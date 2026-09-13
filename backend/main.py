import uuid
import os
import shutil
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from google import genai
from pydantic import BaseModel
import chromadb

load_dotenv()
app = FastAPI()

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://document-qa-rag-tau.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up the Gemini client and a persistent ChromaDB store
gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="documents")

# Pydantic model for the question endpoint
class Question(BaseModel):
    query: str

@app.get("/")
def health_check():
    return {"status": "running"}

@app.get("/documents")
def list_documents():
    all_data = collection.get()
    filenames = set()
    if all_data and "metadatas" in all_data and all_data["metadatas"]:
        for metadata in all_data["metadatas"]:
            if metadata and "filename" in metadata:
                filenames.add(metadata["filename"])
    return {"documents": list(filenames)}

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        return {"error": "Only PDF files are supported."}
    
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    reader = PdfReader(temp_path)
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    
    all_chunks = []
    all_metadatas = []
    
    for page_num, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if not page_text.strip():
            continue
        page_chunks = splitter.split_text(page_text)
        for chunk in page_chunks:
            all_chunks.append(chunk)
            all_metadatas.append({"filename": file.filename, "page": page_num})
            
    os.remove(temp_path)
    
    if not all_chunks:
        return {"error": "No readable text found in this PDF. It may be a scanned image."}
        
    embeddings = []
    for chunk in all_chunks:
        result = gemini_client.models.embed_content(
            model="gemini-embedding-001",
            contents=chunk
        )
        embeddings.append(result.embeddings[0].values)
        
    chunk_ids = [str(uuid.uuid4()) for _ in all_chunks]
    
    collection.add(
        documents=all_chunks,
        embeddings=embeddings,
        metadatas=all_metadatas,
        ids=chunk_ids
    )
    
    return {
        "filename": file.filename,
        "num_pages": len(reader.pages),
        "num_chunks": len(all_chunks),
        "total_stored_in_db": collection.count()
    }

@app.post("/ask")
async def ask_question(question: Question):
    # Step 1: Embed user query
    query_embedding = gemini_client.models.embed_content(
        model="gemini-embedding-001",
        contents=question.query
    ).embeddings[0].values

    # Step 2: Query ChromaDB for top results and metadatas
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=3
    )
    
    # Safely extract chunks and metadatas if available
    retrieved_chunks = results["documents"][0] if results["documents"] and len(results["documents"]) > 0 else []
    retrieved_metadatas = results["metadatas"][0] if results["metadatas"] and len(results["metadatas"]) > 0 else []

    # Step 3: Handle empty database or no matches
    if not retrieved_chunks:
        return {
            "question": question.query, 
            "answer": "No documents have been uploaded yet. Please upload a PDF first.", 
            "sources": []
        }

    # Step 4: Build context and generate answer
    context = "\n\n".join(retrieved_chunks)
    prompt = f"""Answer the question using only the context below. If the answer isn't in the context, say you don't know.

Context:
{context}

Question: {question.query}

Answer:"""

    response = gemini_client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt
    )

    # Step 5: Map chunks and metadata into a clean source list for citations
    sources = [
        {
            "text": chunk, 
            "filename": meta.get("filename", "Unknown"), 
            "page": meta.get("page", 1)
        }
        for chunk, meta in zip(retrieved_chunks, retrieved_metadatas)
    ]

    return {
        "question": question.query,
        "answer": response.text,
        "sources": sources
    }