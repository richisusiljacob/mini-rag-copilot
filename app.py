import os
from dotenv import load_dotenv
from anthropic import Anthropic

import json
from pathlib import Path
from typing import List

import faiss
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from fastapi.middleware.cors import CORSMiddleware

INDEX_DIR = Path("index")
DOCS_PATH = INDEX_DIR / "docs.json"
FAISS_PATH = INDEX_DIR / "docs.faiss"

app = FastAPI(title="Mini RAG Copilot")
load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load once on startup
model = SentenceTransformer("all-MiniLM-L6-v2")
index = faiss.read_index(str(FAISS_PATH))
docs = json.loads(DOCS_PATH.read_text(encoding="utf-8"))

class AskRequest(BaseModel):
    question: str
    top_k: int = 3

class Source(BaseModel):
    doc_id: str
    excerpt: str
    score: float

class AskResponse(BaseModel):
    answer: str
    sources: List[Source]

def retrieve(query: str, top_k: int = 3):
    q_emb = model.encode([query], normalize_embeddings=True)
    scores, idxs = index.search(q_emb, top_k)

    results = []
    for score, idx in zip(scores[0], idxs[0]):
        if idx == -1:
            continue
        text = docs[idx]["text"]
        excerpt = text[:220].replace("\n", " ")
        results.append({"doc_id": docs[idx]["id"], "excerpt": excerpt, "score": float(score)})
    return results

@app.get("/health")
def health():
    return {"status": "ok", "docs": len(docs)}

@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    hits = retrieve(req.question, req.top_k)

    if not hits:
        return AskResponse(answer="No relevant info found in the knowledge base.", sources=[])

    try:
        # Build context
        context_blocks = []
        for i, h in enumerate(hits, start=1):
            full_doc = next((d for d in docs if d.get("id") == h["doc_id"]), None)
            full_text = full_doc.get("text") if full_doc else h["excerpt"]
            context_blocks.append(f"[{i}] Source: {h['doc_id']}\n{full_text}")

        context = "\n\n".join(context_blocks)

        prompt = f"""
You are an incident support copilot.
Answer the user's question using ONLY the context below.
If the answer is not in the context, say: "I don't have enough information in the documents."
Include citations like [1], [2] that correspond to the sources.

Question: {req.question}

Context:
{context}
"""

        # IMPORTANT: use a widely available model first
        msg = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=300,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )

        answer_text = msg.content[0].text
        return AskResponse(answer=answer_text, sources=[Source(**h) for h in hits])

    except Exception as e:
        # Return the real error in the response so we can fix it quickly
        return AskResponse(
            answer=f"Claude error: {type(e).__name__}: {e}",
            sources=[Source(**h) for h in hits],
        )
