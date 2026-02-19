import os
import json
from pathlib import Path

import faiss
from sentence_transformers import SentenceTransformer

DOCS_DIR = Path("data/docs")
INDEX_DIR = Path("index")
INDEX_DIR.mkdir(exist_ok=True)

def load_docs():
    docs = []
    for fp in DOCS_DIR.glob("*.txt"):
        text = fp.read_text(encoding="utf-8").strip()
        docs.append({"id": fp.name, "text": text})
    return docs

def main():
    docs = load_docs()
    if not docs:
        raise RuntimeError("No documents found in data/docs")

    model = SentenceTransformer("all-MiniLM-L6-v2")
    texts = [d["text"] for d in docs]
    embeddings = model.encode(texts, normalize_embeddings=True)

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)  # cosine similarity with normalized vectors
    index.add(embeddings)

    faiss.write_index(index, str(INDEX_DIR / "docs.faiss"))
    (INDEX_DIR / "docs.json").write_text(json.dumps(docs, indent=2), encoding="utf-8")

    print(f"✅ Indexed {len(docs)} docs. Saved to {INDEX_DIR}/")

if __name__ == "__main__":
    main()
