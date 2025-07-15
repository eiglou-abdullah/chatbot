from google import genai
from pathlib import Path
import chromadb
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.document_loaders import Docx2txtLoader
from google.genai.types import EmbedContentConfig
import os
from dotenv import load_dotenv
load_dotenv()
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


chroma_client = chromadb.PersistentClient(path="chroma_db")


client = genai.Client(api_key=GOOGLE_API_KEY)



def load_and_split_docx(file_path: str):
    """Loads a DOCX file and splits it into pages/sections."""
    loader = Docx2txtLoader(file_path)
    documents = loader.load()
    # You might want to split the documents further if needed
    return documents

# Example usage: Upload a DOCX and process it


# Make path cross-platform and relative
docx_file_path = Path(__file__).parent / "data" / "Sample FAQs.docx"

docx_documents = load_and_split_docx(docx_file_path)

# Now you can proceed with RAG operations on docx_documents
# Replace print statements with logging.info
logging.info(f"Loaded {len(docx_documents)} sections from the DOCX file")

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)
d_documents = text_splitter.split_documents(docx_documents)


document_texts = [doc.page_content for doc in d_documents]

docx_embeddings_response = client.models.embed_content(
    model="models/text-embedding-004",
    contents=document_texts,  # Use the extracted text content
    config=EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
)
pdf_doc_embeddings = [emb.values for emb in docx_embeddings_response.embeddings]

# Replace print statements with logging.info
logging.info(f"Generated Length {len(pdf_doc_embeddings)} embeddings")
logging.info(f"Dimensions of first embedding {len(pdf_doc_embeddings[0])}")

collection = chroma_client.get_or_create_collection(name="knowledge_base1")

try:
    collection.add(
        documents=document_texts,
        embeddings=pdf_doc_embeddings,
        ids=[f"doc_{i}" for i in range(len(document_texts))]
    )
    # Replace print statements with logging.info
    logging.info(f"Added {len(d_documents)} PDF pages to the knowledge base.")
except Exception as e:
    # Replace print statements with logging.warning
    logging.warning(f"Could not add PDF documents to collection, potentially they already exist: {e}")

# Replace print statements with logging.info
logging.info(f"Total documents in collection: {collection.count()}")

user_question = "Do i need to manually start and stop the recording?"

# Embed the user query using the same model (use task_type RETRIEVAL_QUERY for queries)
query_response = client.models.embed_content(
    model="models/text-embedding-004",
    contents=[user_question],
    config=EmbedContentConfig(task_type="RETRIEVAL_QUERY")
)
query_vector = query_response.embeddings[0].values
# query_vector

# Use ChromaDB to find the most similar document(s) to the query
results = collection.query(
    query_embeddings=[query_vector],
    n_results=5,  # fetch top 2 most similar docs
    # Remove 'ids' from the include list as it's not a valid option
    include=["documents", "distances"]
)
# Replace print statements with logging.info
logging.info(results)


prompt = f"Context:\n{results}\n\nQuestion:\n{user_question}\n\nAnswer the question using only the context above."
resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
# Replace print statements with logging.info
logging.info(resp.text)