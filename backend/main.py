import uuid
import os
import shutil
from fastapi import FastAPI, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from google import genai
from google.genai import errors as genai_errors
from pydantic import BaseModel
import ollama
from sqlalchemy import create_engine, text
from auth import hash_password, verify_password, create_access_token, get_current_user

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

# Set up the Gemini client and Database engine
gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
db_engine = create_engine(os.environ["DATABASE_URL"])

def get_embedding(text_content: str, mode: str):
    if mode == "local":
        try:
            result = ollama.embed(model="nomic-embed-text", input=text_content)
            return result["embeddings"][0]
        except ConnectionError:
            raise RuntimeError("Local mode isn't available on this deployment — Ollama isn't running here. Clone the repo and run it locally to use Local mode.")
    else:
        result = gemini_client.models.embed_content(model="gemini-embedding-001", contents=text_content)
        return result.embeddings[0].values

def generate_answer(prompt: str, mode: str):
    if mode == "local":
        try:
            response = ollama.chat(model="gemma3:4b", messages=[{"role": "user", "content": prompt}])
            return response["message"]["content"]
        except ConnectionError:
            raise RuntimeError("Local mode isn't available on this deployment — Ollama isn't running here. Clone the repo and run it locally to use Local mode.")
    else:
        response = gemini_client.models.generate_content(model="gemini-3.5-flash-lite", contents=prompt)
        return response.text

# Storage & Retrieval Helpers with pgvector
def get_table_name(mode: str) -> str:
    return "chunks_local" if mode == "local" else "chunks_cloud"

def store_chunks(user_id: int, filename: str, chunks: list, metadatas: list, embeddings: list, mode: str):
    table = get_table_name(mode)
    with db_engine.connect() as conn:
        for chunk, meta, embedding in zip(chunks, metadatas, embeddings):
            conn.execute(
                text(f"""
                    INSERT INTO {table} (user_id, filename, page, text, embedding)
                    VALUES (:user_id, :filename, :page, :text, CAST(:embedding AS vector))
                """),
                {
                    "user_id": user_id,
                    "filename": meta["filename"],
                    "page": meta["page"],
                    "text": chunk,
                    "embedding": str(embedding),
                }
            )
        conn.commit()

def search_chunks(user_id: int, query_embedding: list, mode: str, limit: int = 3):
    table = get_table_name(mode)
    with db_engine.connect() as conn:
        results = conn.execute(
            text(f"""
                SELECT text, filename, page
                FROM {table}
                WHERE user_id = :user_id
                ORDER BY embedding <=> CAST(:query_embedding AS vector)
                LIMIT :limit
            """),
            {"user_id": user_id, "query_embedding": str(query_embedding), "limit": limit}
        ).fetchall()
    return results

def list_user_documents(user_id: int, mode: str):
    table = get_table_name(mode)
    with db_engine.connect() as conn:
        results = conn.execute(
            text(f"SELECT DISTINCT filename FROM {table} WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchall()
    return [row.filename for row in results]

def delete_user_document(user_id: int, filename: str, mode: str) -> bool:
    table = get_table_name(mode)
    with db_engine.connect() as conn:
        result = conn.execute(
            text(f"DELETE FROM {table} WHERE user_id = :user_id AND filename = :filename"),
            {"user_id": user_id, "filename": filename}
        )
        conn.commit()
        return result.rowcount > 0

# Pydantic models for requests
class Question(BaseModel):
    query: str
    history: list[dict] = []
    mode: str = "cloud"
    conversation_id: int

class SignupRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

def needs_reformulation(query: str) -> bool:
    trigger_words = ["it", "that", "this", "those", "these", "second", "first", "also", "previous", "again", "more"]
    words = query.lower().split()
    return len(words) <= 6 or any(word in trigger_words for word in words)

@app.get("/")
def health_check():
    return {"status": "running"}

@app.post("/signup")
async def signup(request: SignupRequest):
    with db_engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": request.email}
        ).fetchone()
        if existing:
            return {"error": "An account with this email already exists."}
        hashed = hash_password(request.password)
        result = conn.execute(
            text("INSERT INTO users (email, hashed_password) VALUES (:email, :hashed) RETURNING id"),
            {"email": request.email, "hashed": hashed}
        )
        user_id = result.fetchone()[0]
        conn.commit()
    token = create_access_token(user_id, request.email)
    return {"token": token, "email": request.email}

@app.post("/login")
async def login(request: LoginRequest):
    with db_engine.connect() as conn:
        user = conn.execute(
            text("SELECT id, hashed_password FROM users WHERE email = :email"),
            {"email": request.email}
        ).fetchone()
    if not user or not verify_password(request.password, user.hashed_password):
        return {"error": "Invalid email or password."}
    token = create_access_token(user.id, request.email)
    return {"token": token, "email": request.email}

@app.post("/conversations")
def create_conversation(current_user: dict = Depends(get_current_user)):
    with db_engine.connect() as conn:
        result = conn.execute(
            text("INSERT INTO conversations (user_id) VALUES (:user_id) RETURNING id, title, created_at"),
            {"user_id": current_user["user_id"]}
        )
        row = result.fetchone()
        conn.commit()
    return {"id": row.id, "title": row.title, "created_at": row.created_at.isoformat()}

@app.get("/conversations")
def list_conversations(current_user: dict = Depends(get_current_user)):
    with db_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, title, created_at FROM conversations WHERE user_id = :user_id ORDER BY created_at DESC"),
            {"user_id": current_user["user_id"]}
        ).fetchall()
    return {"conversations": [{"id": r.id, "title": r.title, "created_at": r.created_at.isoformat()} for r in rows]}

@app.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: int, current_user: dict = Depends(get_current_user)):
    with db_engine.connect() as conn:
        owner_check = conn.execute(
            text("SELECT user_id FROM conversations WHERE id = :id"),
            {"id": conversation_id}
        ).fetchone()
        if not owner_check or owner_check.user_id != current_user["user_id"]:
            return {"error": "Conversation not found."}
        rows = conn.execute(
            text("SELECT role, text, created_at FROM chat_history WHERE conversation_id = :cid ORDER BY created_at ASC"),
            {"cid": conversation_id}
        ).fetchall()
    return {"messages": [{"role": r.role, "text": r.text} for r in rows]}

@app.get("/documents")
def list_documents(mode: str = "cloud", current_user: dict = Depends(get_current_user)):
    filenames = list_user_documents(current_user["user_id"], mode)
    return {"documents": filenames}

@app.delete("/documents/{filename}")
async def delete_document(filename: str, mode: str = "cloud", current_user: dict = Depends(get_current_user)):
    deleted = delete_user_document(current_user["user_id"], filename, mode)
    if not deleted:
        return {"error": f'No document found matching "{filename}".'}
    return {"success": True, "message": f"Deleted {filename} successfully."}

@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...), mode: str = Form("cloud"), current_user: dict = Depends(get_current_user)):
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
    total_chunks = len(all_chunks)

    try:
        for chunk in all_chunks:
            embeddings.append(get_embedding(chunk, mode))
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
    except RuntimeError as e:
        return {"error": str(e)}

    store_chunks(current_user["user_id"], file.filename, all_chunks, all_metadatas, embeddings, mode)
    
    result = {
        "filename": file.filename,
        "num_pages": len(reader.pages),
        "num_chunks": len(all_chunks),
        "mode": mode
    }

    if hit_limit:
        result["warning"] = f"Uploaded and processed {chunks_processed} of {total_chunks} chunks before hitting the daily limit."

    return result

@app.post("/ask")
async def ask_question(question: Question, current_user: dict = Depends(get_current_user)):
    search_query = question.query

    # Step 1: Reformulate follow-up questions using history context if needed
    if question.history and needs_reformulation(question.query):
        history_text = "\n".join([f"{m['role']}: {m['text']}" for m in question.history[-4:]])
        rewrite_prompt = f"""Given this conversation history:
{history_text}

Rewrite this follow-up question as a standalone question, using context from the history. Only output the rewritten question, nothing else.

Follow-up question: {question.query}"""

        try:
            search_query = generate_answer(rewrite_prompt, question.mode).strip()
        except genai_errors.ClientError as e:
            if e.code == 429:
                search_query = question.query  # Fall back to original query if limited
            else:
                raise
        except RuntimeError as e:
            return {"question": question.query, "answer": str(e), "sources": []}

    # Step 2: Embed user query with rate limit and runtime handling
    try:
        query_embedding = get_embedding(search_query, question.mode)
    except genai_errors.ClientError as e:
        if e.code == 429:
            return {
                "question": question.query,
                "answer": "I've hit today's API usage limit. Please try again later or tomorrow.",
                "sources": []
            }
        raise
    except RuntimeError as e:
        return {"question": question.query, "answer": str(e), "sources": []}

    # Step 3: Query target pgvector table for top results
    rows = search_chunks(current_user["user_id"], query_embedding, question.mode)
    retrieved_chunks = [row.text for row in rows]
    retrieved_metadatas = [{"filename": row.filename, "page": row.page} for row in rows]

    # Step 4: Handle empty database or no matches
    if not retrieved_chunks:
        return {
            "question": question.query, 
            "answer": "No documents have been uploaded yet in this mode. Please upload a PDF first.", 
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
        answer_text = generate_answer(prompt, question.mode)
    except genai_errors.ClientError as e:
        if e.code == 429:
            return {
                "question": question.query,
                "answer": "I've hit today's API usage limit. Please try again later or tomorrow.",
                "sources": []
            }
        raise
    except RuntimeError as e:
        return {"question": question.query, "answer": str(e), "sources": []}

    # Save chat history and auto-title conversation
    with db_engine.connect() as conn:
        conn.execute(
            text("INSERT INTO chat_history (user_id, conversation_id, role, text) VALUES (:uid, :cid, 'user', :text)"),
            {"uid": current_user["user_id"], "cid": question.conversation_id, "text": question.query}
        )
        conn.execute(
            text("INSERT INTO chat_history (user_id, conversation_id, role, text) VALUES (:uid, :cid, 'assistant', :text)"),
            {"uid": current_user["user_id"], "cid": question.conversation_id, "text": answer_text}
        )
        conn.execute(
            text("""
                UPDATE conversations SET title = :title
                WHERE id = :cid AND title = 'New Chat'
            """),
            {"title": question.query[:50], "cid": question.conversation_id}
        )
        conn.commit()

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
        "answer": answer_text,
        "sources": sources
    }