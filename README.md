# 🧠 Multi-Document RAG Chatbot

Upload multiple PDF files and ask questions across all of them at once. The chatbot retrieves the most relevant excerpts, answers with cited sources, and remembers conversation context — powered by Claude AI.

## Features

- **Multiple PDFs** — add and remove documents at any time
- **TF-IDF retrieval** — fast semantic search across all chunks (no internet required for indexing)
- **Cited answers** — every response includes `[filename · page]` references
- **Conversation memory** — maintains last 10 turns of context
- **Live stats** — chunks indexed, documents loaded, conversation turns
- **Works with**: clinical trial protocols, research papers, legal documents, technical manuals, any text-based PDF

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python · Flask |
| Retrieval | TF-IDF (scikit-learn) — no vector DB dependency |
| AI | Anthropic Claude API (`claude-sonnet-4-20250514`) |
| PDF parsing | PyPDF2 |
| Frontend | Vanilla HTML · CSS · JavaScript |

## Quick Start

```bash
git clone https://github.com/szmsk/rag-chatbot.git
cd rag-chatbot
pip install -r requirements.txt
python server.py
# → http://localhost:5000
```

Get API key at [console.anthropic.com](https://console.anthropic.com) — first $5 free.

## How It Works

```
Multiple PDF uploads
        ↓
PyPDF2 extracts text per page
        ↓
Text split into 1200-char overlapping chunks
        ↓
TF-IDF index built (scikit-learn)
        ↓
User asks question
        ↓
Top 5 relevant chunks retrieved (cosine similarity)
        ↓
Claude answers with citations + conversation history
        ↓
Answer + [doc · page] tags displayed in chat
```

## Architecture Notes

- **TF-IDF vs. ChromaDB**: Uses scikit-learn TF-IDF instead of a vector DB — zero external dependencies, runs fully offline, fast enough for up to ~500 documents
- **Chunk size**: 1200 chars with 150-char overlap — balances context richness with retrieval precision
- **Memory**: Last 10 conversation turns kept in Claude context — enables follow-up questions
- **Auto-retry**: If API call fails, error is surfaced cleanly in chat

## Project Structure

```
rag-chatbot/
├── server.py           # Flask + TF-IDF + PyPDF2 + Claude API
├── requirements.txt
├── public/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── README.md
```

## Author

Built by **Szymon Kloskowski**

**Contact:** kloskowskiszymon@wp.pl
**GitHub:** [github.com/szmsk](https://github.com/szmsk)
**LinkedIn:** [linkedin.com/in/szymon-kloskowski](https://linkedin.com/in/szymon-kloskowski)

MIT License
