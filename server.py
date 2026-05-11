"""
Multi-Document RAG Chatbot — Backend
Multiple PDFs → TF-IDF vector store → Claude answers with citations + memory
"""
import os, io, json, re, time, uuid
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import anthropic
import PyPDF2
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

app = Flask(__name__, static_folder='public', static_url_path='')
CORS(app)

# ── In-memory knowledge base per session ─────────────────────────────────────
# kb_id -> {
#   "chunks":    [{"text":str, "doc":str, "page":int, "chunk_id":str}],
#   "vectorizer": TfidfVectorizer,
#   "matrix":    np.array,
#   "docs":      {filename: {pages, chars, chunks}},
#   "history":   [{role, content}],
#   "api_key":   str,
# }
knowledge_bases = {}

CHUNK_SIZE    = 1200
CHUNK_OVERLAP = 150
MAX_CHUNKS    = 5
MAX_HISTORY   = 10   # last N turns kept in context


# ── PDF + chunking ────────────────────────────────────────────────────────────

def extract_pdf(file_bytes: bytes) -> list[dict]:
    """Extract text per page from PDF."""
    reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages.append({"page": i + 1, "text": text.strip()})
    return pages


def make_chunks(pages: list[dict], filename: str) -> list[dict]:
    """Split pages into overlapping chunks with metadata."""
    chunks = []
    for page in pages:
        text = page["text"]
        start = 0
        while start < len(text):
            end   = min(start + CHUNK_SIZE, len(text))
            chunk = text[start:end]
            if end < len(text):
                last_break = max(chunk.rfind(". "), chunk.rfind("\n"))
                if last_break > CHUNK_SIZE // 2:
                    end   = start + last_break + 1
                    chunk = text[start:end]
            if len(chunk.strip()) > 60:
                chunks.append({
                    "text":     chunk.strip(),
                    "doc":      filename,
                    "page":     page["page"],
                    "chunk_id": str(uuid.uuid4())[:8],
                })
            start = end - CHUNK_OVERLAP
    return chunks


def rebuild_index(kb: dict):
    """Rebuild TF-IDF matrix after adding new documents."""
    texts = [c["text"] for c in kb["chunks"]]
    if not texts:
        kb["vectorizer"] = None
        kb["matrix"]     = None
        return
    vec = TfidfVectorizer(
        max_features=8000,
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=1,
    )
    matrix = vec.fit_transform(texts)
    kb["vectorizer"] = vec
    kb["matrix"]     = matrix


def retrieve(kb: dict, query: str, k: int = MAX_CHUNKS) -> list[dict]:
    """Return top-k relevant chunks for a query."""
    if not kb.get("vectorizer") or kb["matrix"] is None:
        return kb["chunks"][:k]
    qv     = kb["vectorizer"].transform([query])
    scores = cosine_similarity(qv, kb["matrix"])[0]
    top_k  = np.argsort(scores)[::-1][:k]
    # Filter out near-zero scores
    return [kb["chunks"][i] for i in top_k if scores[i] > 0.01]


def format_context(chunks: list[dict]) -> str:
    seen = set()
    parts = []
    for c in chunks:
        key = (c["doc"], c["page"])
        label = f'[{c["doc"]} · p.{c["page"]}]'
        if key not in seen:
            seen.add(key)
        parts.append(f"{label}\n{c['text']}")
    return "\n\n---\n\n".join(parts)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("public", "index.html")


@app.route("/api/kb/new", methods=["POST"])
def new_kb():
    """Create a new knowledge base, return its ID."""
    kb_id = str(uuid.uuid4())[:12]
    knowledge_bases[kb_id] = {
        "chunks":     [],
        "vectorizer": None,
        "matrix":     None,
        "docs":       {},
        "history":    [],
        "api_key":    "",
    }
    return jsonify({"kb_id": kb_id})


@app.route("/api/kb/<kb_id>/upload", methods=["POST"])
def upload(kb_id):
    """Upload and index a PDF into an existing knowledge base."""
    if kb_id not in knowledge_bases:
        return jsonify({"error": "Knowledge base not found"}), 404

    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400

    file    = request.files["file"]
    api_key = request.form.get("apiKey", "").strip()

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files supported"}), 400
    if not api_key:
        return jsonify({"error": "API key required"}), 400

    kb = knowledge_bases[kb_id]
    kb["api_key"] = api_key

    # Check duplicate
    if file.filename in kb["docs"]:
        return jsonify({"error": f'"{file.filename}" already uploaded'}), 400

    try:
        file_bytes = file.read()
        if len(file_bytes) > 25 * 1024 * 1024:
            return jsonify({"error": "File too large (max 25 MB)"}), 400

        pages  = extract_pdf(file_bytes)
        if not pages:
            return jsonify({"error": "Could not extract text. PDF may be scanned/image-based."}), 400

        chunks = make_chunks(pages, file.filename)
        kb["chunks"].extend(chunks)
        kb["docs"][file.filename] = {
            "pages":  len(pages),
            "chars":  sum(len(p["text"]) for p in pages),
            "chunks": len(chunks),
        }
        rebuild_index(kb)

        return jsonify({
            "filename":   file.filename,
            "pages":      len(pages),
            "chunks":     len(chunks),
            "total_docs": len(kb["docs"]),
            "total_chunks": len(kb["chunks"]),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/kb/<kb_id>/remove", methods=["POST"])
def remove_doc(kb_id):
    """Remove a document from the knowledge base."""
    if kb_id not in knowledge_bases:
        return jsonify({"error": "Not found"}), 404
    data     = request.get_json()
    filename = data.get("filename", "")
    kb       = knowledge_bases[kb_id]
    if filename not in kb["docs"]:
        return jsonify({"error": "Document not found"}), 404
    kb["chunks"] = [c for c in kb["chunks"] if c["doc"] != filename]
    del kb["docs"][filename]
    rebuild_index(kb)
    return jsonify({"removed": filename, "total_chunks": len(kb["chunks"])})


@app.route("/api/kb/<kb_id>/ask", methods=["POST"])
def ask(kb_id):
    """Answer a question using RAG over the knowledge base."""
    if kb_id not in knowledge_bases:
        return jsonify({"error": "Knowledge base not found"}), 404

    data     = request.get_json()
    question = data.get("question", "").strip()
    kb       = knowledge_bases[kb_id]
    api_key  = kb.get("api_key", "")

    if not question:
        return jsonify({"error": "Question required"}), 400
    if not api_key:
        return jsonify({"error": "API key missing — re-upload a document"}), 400
    if not kb["chunks"]:
        return jsonify({"error": "No documents in knowledge base. Upload PDFs first."}), 400

    # Retrieve relevant chunks
    chunks  = retrieve(kb, question)
    context = format_context(chunks)

    # Build conversation history for Claude
    history_msgs = []
    for turn in kb["history"][-MAX_HISTORY:]:
        history_msgs.append({"role": turn["role"], "content": turn["content"]})

    doc_list = ", ".join(f'"{d}"' for d in kb["docs"].keys())

    system = f"""You are an expert research assistant with access to a knowledge base containing {len(kb['docs'])} document(s): {doc_list}.

You answer questions based ONLY on the provided document excerpts. Rules:
- Always cite your sources using the format [filename · p.N]
- If a question spans multiple documents, synthesise across them
- If the documents don't contain enough information, say so clearly
- Be precise — include numbers, dates, names exactly as in the documents
- Keep answers well-structured; use paragraphs for long answers
- You have access to conversation history — refer back to it when relevant"""

    user_content = f"""Relevant excerpts from the knowledge base:

{context}

---

Question: {question}"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        t0 = time.time()

        messages = history_msgs + [{"role": "user", "content": user_content}]

        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1200,
            system=system,
            messages=messages,
        )
        answer = msg.content[0].text.strip()
        ms     = round((time.time() - t0) * 1000)

        # Save to history (concise version to keep context manageable)
        kb["history"].append({"role": "user",      "content": question})
        kb["history"].append({"role": "assistant",  "content": answer})
        if len(kb["history"]) > MAX_HISTORY * 2:
            kb["history"] = kb["history"][-(MAX_HISTORY * 2):]

        # Build citations list
        citations = []
        seen = set()
        for c in chunks:
            key = (c["doc"], c["page"])
            if key not in seen:
                seen.add(key)
                citations.append({"doc": c["doc"], "page": c["page"]})

        return jsonify({
            "answer":    answer,
            "citations": citations,
            "ms":        ms,
            "chunks_used": len(chunks),
        })

    except anthropic.AuthenticationError:
        return jsonify({"error": "Invalid API key"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/kb/<kb_id>/clear_history", methods=["POST"])
def clear_history(kb_id):
    if kb_id not in knowledge_bases:
        return jsonify({"error": "Not found"}), 404
    knowledge_bases[kb_id]["history"] = []
    return jsonify({"cleared": True})


@app.route("/api/kb/<kb_id>/info", methods=["GET"])
def kb_info(kb_id):
    if kb_id not in knowledge_bases:
        return jsonify({"error": "Not found"}), 404
    kb = knowledge_bases[kb_id]
    return jsonify({
        "docs":         kb["docs"],
        "total_chunks": len(kb["chunks"]),
        "history_turns": len(kb["history"]) // 2,
    })


@app.route("/api/status")
def status():
    return jsonify({"status": "ok", "kbs": len(knowledge_bases)})


if __name__ == "__main__":
    print("🧠 RAG Chatbot running on http://localhost:5000")
    app.run(debug=False, port=5000)
