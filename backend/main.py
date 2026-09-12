from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from google import genai
from pydantic import BaseModel
import chromadb
import shutil
import os

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

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    # Fix 1: Reject non-PDF files early
    if not file.filename.lower().endswith(".pdf"):
        return {"error": "Only PDF files are supported."}

    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    reader = PdfReader(temp_path)
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() or ""

    # Fix 2: Handle empty or unreadable PDFs
    if not full_text.strip():
        os.remove(temp_path)
        return {"error": "No readable text found in this PDF. It may be a scanned image."}

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    chunks = splitter.split_text(full_text)

    os.remove(temp_path)

    # Generate an embedding for each chunk and store it
    embeddings = []
    for chunk in chunks:
        result = gemini_client.models.embed_content(
            model="gemini-embedding-001",
            contents=chunk
        )
        embeddings.append(result.embeddings[0].values)

    chunk_ids = [f"{file.filename}_{i}" for i in range(len(chunks))]

    collection.add(
        documents=chunks,
        embeddings=embeddings,
        ids=chunk_ids
    )

    return {
        "filename": file.filename,
        "num_pages": len(reader.pages),
        "num_chunks": len(chunks),
        "total_stored_in_db": collection.count()
    }

@app.post("/ask")
async def ask_question(question: Question):
    # Step 1: embed the user's question the same way we embedded chunks
    query_embedding = gemini_client.models.embed_content(
        model="gemini-embedding-001",
        contents=question.query
    ).embeddings[0].values

    # Step 2: find the most similar stored chunks
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=3
    )
    
    # Safely get retrieved chunks
    retrieved_chunks = results["documents"][0] if results["documents"] and len(results["documents"]) > 0 else []

    # Fix 3: Handle questions when the database is empty
    if not retrieved_chunks:
        return {
            "question": question.query,
            "answer": "No documents have been uploaded yet. Please upload a PDF first.",
            "chunks_used": []
        }

    # Step 3: build a prompt using the retrieved chunks as context
    context = "\n\n".join(retrieved_chunks)
    prompt = f"""Answer the question using only the context below. If the answer isn't in the context, say you don't know.

Context:
{context}

Question: {question.query}

Answer:"""

    # Step 4: generate the answer
    response = gemini_client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt
    )

    return {
        "question": question.query,
        "answer": response.text,
        "chunks_used": retrieved_chunks
    }