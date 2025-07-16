from google import genai
from google.genai import types
from pathlib import Path
import chromadb
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import Docx2txtLoader
import os
from dotenv import load_dotenv
import logging
import numpy as np

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    logging.error("GOOGLE_API_KEY not set in environment.")
    exit(1)

chroma_client = chromadb.PersistentClient(path="chroma_db")
client = genai.Client(api_key=GOOGLE_API_KEY)

def load_and_split_docx(file_path: str):
    loader = Docx2txtLoader(file_path)
    documents = loader.load()
    return documents

DATA_DIR = Path(__file__).parent / "data"
docx_files = list(DATA_DIR.glob("*.docx"))

if not docx_files:
    logging.error(f"No DOCX files found in {DATA_DIR}")
    exit(1)

for docx_file in docx_files:
    collection_name = docx_file.stem  # e.g., "Privacy_Policy"
    logging.info(f"Processing {docx_file.name} into collection '{collection_name}'")

    try:
        docx_documents = load_and_split_docx(str(docx_file))
        logging.info(f"Loaded {len(docx_documents)} sections from {docx_file.name}")

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        d_documents = text_splitter.split_documents(docx_documents)
        document_texts = [doc.page_content for doc in d_documents]

        # Embed the document chunks
        docx_embeddings_response = client.models.embed_content(
            model="gemini-embedding-001",
            contents=document_texts,
            config=types.EmbedContentConfig(output_dimensionality=3072, task_type="RETRIEVAL_DOCUMENT")
        )
        if not docx_embeddings_response.embeddings:
            logging.error(f"Embedding API returned no embeddings for {docx_file.name}.")
            continue

        pdf_doc_embeddings = [emb.values for emb in docx_embeddings_response.embeddings if emb and emb.values]
        if not pdf_doc_embeddings:
            logging.error(f"No valid embeddings generated from {docx_file.name}.")
            continue

        pdf_doc_embeddings = np.array(pdf_doc_embeddings, dtype=np.float32)
        logging.info(f"Generated {len(pdf_doc_embeddings)} embeddings for {docx_file.name}")
        logging.info(f"Dimensions of first embedding: {len(pdf_doc_embeddings[0])}")

        collection = chroma_client.get_or_create_collection(name=collection_name)
        try:
            collection.add(
                documents=document_texts,
                embeddings=pdf_doc_embeddings,
                ids=[f"{collection_name}_doc_{i}" for i in range(len(document_texts))]
            )
            logging.info(f"Added {len(d_documents)} sections to collection '{collection_name}'.")
        except Exception as e:
            logging.warning(f"Could not add documents to collection '{collection_name}': {e}")

        logging.info(f"Total documents in collection '{collection_name}': {collection.count()}")

    except Exception as e:
        logging.error(f"Failed to process {docx_file.name}: {e}")

logging.info("All files processed.")