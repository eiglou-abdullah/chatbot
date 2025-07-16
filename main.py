import os
from typing import List, Dict
from instructions import instruct
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi.responses import Response

import chromadb
from google import genai
from chromadb.utils import embedding_functions
from google.genai.types import EmbedContentConfig

from agents import Agent, Runner, OpenAIChatCompletionsModel, set_tracing_disabled
from openai import AsyncOpenAI
from agents.run import RunConfig
from agents.tool import function_tool
from google.genai import types

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY environment variable not set.")

chroma_client = chromadb.PersistentClient(path="chroma_db")
collection = chroma_client.get_or_create_collection(name="knowledge_base1")

client = genai.Client(api_key=GOOGLE_API_KEY)

external_client = AsyncOpenAI(api_key=GOOGLE_API_KEY, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")

MODEL_NAME = "gemini-2.5-flash"
model = OpenAIChatCompletionsModel(
    model=MODEL_NAME,
    openai_client=external_client
)
config = RunConfig(model=model, model_provider=external_client, tracing_disabled=True)
set_tracing_disabled(True)



@function_tool
def get_answer_from_collection(collection_name: str, query: str) -> str:
    """
    Query a specific ChromaDB collection for context and generate an answer.

    Args:
        collection_name (str): The name of the ChromaDB collection (should match the document name without .docx).
        query (str): The user's question about the document.

    Returns:
        str: An answer generated using only the context from the specified document collection.

    Usage:
        Use this tool to answer questions about a specific document. The collection_name should match the document's filename (without extension) in the /data directory.
        Example: collection_name='Privacy_Policy', query='What data do you collect?'
    """
    # Embed the query using the same model/dimensionality as set_vector_store.py
    query_response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=[query],
        config=types.EmbedContentConfig(output_dimensionality=3072, task_type="RETRIEVAL_QUERY")
    )
    if not query_response.embeddings:
        raise HTTPException(status_code=500, detail="Embedding API returned no embeddings.")
    query_vector = query_response.embeddings[0].values
    if not query_vector:
        raise HTTPException(status_code=500, detail="Query embedding vector is empty.")

    # Query the specified collection
    collection = chroma_client.get_or_create_collection(name=collection_name)
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=5,
        include=["documents", "distances"]
    )
    prompt = f"Context:\n{results}\n\nQuestion:\n{query}\n\nAnswer the question using only the context above."
    resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return resp.text or "No answer generated."

agent = Agent(
    name="Student Guide",
    instructions=instruct,
    tools=[get_answer_from_collection],
)

# --- In-memory session store (for demo only!) ---
# TODO: For production, replace with a persistent store (e.g., Redis, database)
chat_sessions: Dict[str, List[Dict[str, str]]] = {}

# --- Pydantic schemas ---
class MessageInput(BaseModel):
    session_id: str = Field(..., description="Unique identifier for the chat session")
    message: str = Field(..., min_length=1, description="The user's message")

class ChatResponse(BaseModel):
    session_id: str
    response: str

# --- FastAPI app ---
app = FastAPI(
    title="Student Guider Chatbot API",
    description="API for interacting with the Student Guider chatbot."
)

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,  # Use env var for production
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

from fastapi.responses import JSONResponse
from fastapi.exception_handlers import RequestValidationError
from fastapi.exceptions import RequestValidationError as FastAPIRequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error. Please try again later."})

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.exception_handler(FastAPIRequestValidationError)
async def validation_exception_handler(request: Request, exc: FastAPIRequestValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logging.debug(f"Received request: {request.method} {request.url}")
    response = await call_next(request)
    logging.debug(f"Response status: {response.status_code}")
    return response

@app.options("/chat")
async def options_chat_endpoint():
    return Response(status_code=200)

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: MessageInput):
    session_id = payload.session_id
    user_message = payload.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="`message` cannot be empty.")

    history = chat_sessions.setdefault(session_id, [])
    history.append({"role": "user", "content": user_message})

    try:
        result = await Runner.run(
            starting_agent=agent,
            input=history,
            run_config=config
        )
        bot_reply = result.final_output or "🤖 (no reply generated)"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    history.append({"role": "assistant", "content": bot_reply})
    return ChatResponse(session_id=session_id, response=bot_reply)

@app.get("/")
def welcome():
    return {
        "message": "👋 Welcome! POST JSON `{ session_id, message }` to /chat.",
        "status": "healthy"
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "message": "Service is running"
    }












