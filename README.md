# Document Q&A (RAG-based)

A retrieval-augmented Q&A system that lets users upload a PDF and ask natural-language questions about its content, using vector search and the Gemini API.

## Status: In Progress

## Tech Stack
- Backend: FastAPI, LangChain, ChromaDB
- AI: Google Gemini (embeddings + generation)
- Frontend: React + TypeScript (in progress)

## How it works
1. PDF is uploaded and split into chunks
2. Each chunk is embedded and stored in ChromaDB
3. User questions are embedded and matched against stored chunks
4. Gemini generates an answer grounded in the retrieved chunks