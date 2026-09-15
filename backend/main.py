import uuid
import os
import shutil
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from google import genai
from google.genai import errors as genai_errors
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

# Pydantic model for the question endpoint with history support
class Question(BaseModel):
    query: str
    history: list[dict] = []

def needs_reformulation(query: str) -> bool:
    trigger_words = ["it", "that", "this", "those", "these", "second", "first", "also", "previous", "again", "more"]
    words = query.lower().split()
    return len(words) <= 6 or any(word in trigger_words for word in words)

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
    chunks_processed = 0
    hit_limit = False
    total_chunks = len(all_chunks)  # Baseline reference

    try:
        for chunk in all_chunks:
            result = gemini_client.models.embed_content(
                model="gemini-embedding-001",
                contents=chunk
            )
            embeddings.append(result.embeddings[0].values)
            chunks_processed += 1
    except genai_errors.ClientError as e:
        if e.code == 429:
            hit_limit = True
            if not embeddings:
                return {"error": "API usage limit reached before any chunks could be embedded. Please try again later."}
            all_chunks = all_chunks[:chunks_processed]
            all_metadatas = all_metadatas[:chunks_processed]
        else:
            raise

    chunk_ids = [str(uuid.uuid4()) for _ in all_chunks]
    
    collection.add(
        documents=all_chunks,
        embeddings=embeddings,
        metadatas=all_metadatas,
        ids=chunk_ids
    )
    
    if hit_limit:
        return {
            "filename": file.filename,
            "num_pages": len(reader.pages),
            "num_chunks": len(all_chunks),
            "total_stored_in_db": collection.count(),
            "warning": f"Uploaded and processed {chunks_processed} of {total_chunks} chunks before hitting the daily limit."
        }

    return {
        "filename": file.filename,
        "num_pages": len(reader.pages),
        "num_chunks": len(all_chunks),
        "total_stored_in_db": collection.count()
    }

@app.post("/ask")
async def ask_question(question: Question):
    search_query = question.query

    # Step 1: Reformulate follow-up questions using history context if needed
    if question.history and needs_reformulation(question.query):
        history_text = "\n".join([f"{m['role']}: {m['text']}" for m in question.history[-4:]])
        rewrite_prompt = f"""Given this conversation history:
{history_text}

Rewrite this follow-up question as a standalone question, using context from the history. Only output the rewritten question, nothing else.

Follow-up question: {question.query}"""

        try:
            rewrite_response = gemini_client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=rewrite_prompt
            )
            search_query = rewrite_response.text.strip()
        except genai_errors.ClientError as e:
            if e.code == 429:
                search_query = question.query  # Fall back to original query if limited
            else:
                raise

    # Step 2: Embed user query with rate limit handling
    try:
        query_embedding = gemini_client.models.embed_content(
            model="gemini-embedding-001",
            contents=search_query
        ).embeddings[0].values
    except genai_errors.ClientError as e:
        if e.code == 429:
            return {
                "question": question.query,
                "answer": "I've hit today's API usage limit. Please try again later or tomorrow.",
                "sources": []
            }
        raise

    # Step 3: Query ChromaDB for top results and metadatas
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=3
    )
    
    retrieved_chunks = results["documents"][0] if results["documents"] and len(results["documents"]) > 0 else []
    retrieved_metadatas = results["metadatas"][0] if results["metadatas"] and len(results["metadatas"]) > 0 else []

    # Step 4: Handle empty database or no matches
    if not retrieved_chunks:
        return {
            "question": question.query, 
            "answer": "No documents have been uploaded yet. Please upload a PDF first.", 
            "sources": []
        }

    # Step 5: Build conversation history context and final prompt
    history_context = ""
    if question.history:
        history_context = "Previous conversation:\n" + "\n".join([f"{m['role']}: {m['text']}" for m in question.history[-4:]]) + "\n\n"

    context = "\n\n".join(retrieved_chunks)
    prompt = f"""{history_context}Answer the question using only the context below. If the answer isn't in the context, say you don't know.

Context:
{context}

Question: {question.query}

Answer:"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt
        )
    except genai_errors.ClientError as e:
        if e.code == 429:
            return {
                "question": question.query,
                "answer": "I've hit today's API usage limit. Please try again later or tomorrow.",
                "sources": []
            }
        raise

    # Step 6: Map chunks and metadata into a clean source list for citations safely
    sources = [
        {
            "text": chunk, 
            "filename": (meta or {}).get("filename", "Unknown"), 
            "page": (meta or {}).get("page", 1)
        }
        for chunk, meta in zip(retrieved_chunks, retrieved_metadatas)
    ]

    return {
        "question": question.query,
        "answer": response.text,
        "sources": sources
    }