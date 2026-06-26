# ADR-002 — Final Production Architecture

| Field       | Value                            |
|-------------|----------------------------------|
| Date        | 2026-06-26                       |
| Authors     | AI Multimedia Platform Team      |
| Supersedes  | —                                |

---

## Context

The original ADR-001 documented the initial production restructuring. Since then, the project has evolved through deployment and testing. This ADR captures the 
**final architecture** — decisions that were validated, decisions that changed, and new decisions made.

---

## Key Decisions Made

### ✅ **Decision 1 — Multi-User Authentication**

**What:** Added user registration, login, and session management with bcrypt password hashing.

**Why:** The project needed to support multiple users with isolated data.

**Implementation:**
- `users` table in SQLite (`id`, `username`, `password_hash`, `created_at`)
- Flask sessions with `SECRET_KEY`
- All routes check `session["user_id"]` for authorization

---

### ✅ **Decision 2 — SQLite for Production Database**

**What:** SQLite with WAL mode, thread-local connections.

**Why:** Simple, reliable, no external database server required. Works on Railway with persistent volumes (as long as deployment doesn't reset).

**Tables:**
| Table | Purpose |
|-------|---------|
| `users` | User accounts |
| `files` | Uploaded file metadata (user‑owned) |
| `transcripts` | Audio/video transcripts (linked to file_id) |
| `summaries` | PDF summaries (linked to file_id) |
| `chats` | Conversation threads with per‑user isolation |

---

### ✅ **Decision 3 — Groq Over Ollama**

**What:** Switched from Ollama to Groq API for summarisation and RAG.

| Aspect              | Ollama                         | Groq                   |
|---------------------|--------------------------------|------------------------|
| **Hosting**         | Requires local daemon          | Cloud API              |
| **Railway Support** | ❌ Not available on free tier | ✅ Works on any tier   |
| **Speed**           | Medium (CPU)                   | Fast (enterprise GPUs) |
| **Cost**            | Free (your hardware)           | Free tier (30 req/min) |
| **Model**           | Llama 3.2 3B                   | Llama 3.1 8B           |

**Implementation:**
- `services/rag_service.py` uses Groq client
- `services/summarization_service.py` uses Groq for PDFs

---

### ✅ **Decision 4 — Faster-Whisper Over OpenAI Whisper**

**What:** Replaced `openai-whisper` with `faster-whisper` (CTranslate2).

| Aspect         | OpenAI Whisper    | Faster-Whisper            |
|----------------|-------------------|---------------------------|
| **Speed**      | Baseline          | 4-5x faster               |
| **Memory**     | Higher            | Lower (int8 quantization) |
| **Build**      | Broken on Railway | Works fine                |
| **VAD Filter** | ❌ None           | ✅ Built-in              |

**Implementation:** `services/transcription_service.py` uses `faster-whisper` with `int8` on CPU, `float16` on GPU.

---

### ✅ **Decision 5 — Remove T5, Keep Only Groq + Template**

**What:** Removed T5-small summariser entirely.

**Why:** T5 caused:
- Worker timeouts on Railway (slow loading)
- Out-of-memory issues (adds ~500MB)
- VERY Low-quality summaries compared to Groq

**Current flow:**
```
PDF → Groq (primary) → Template (fallback)
```

---

### ✅ **Decision 6 — Persistent Storage on Railway**

**What:** Used Railway Volumes mounted at `/app/data`.

**Why:** SQLite and uploaded files must persist between deployments.


---

### ✅ **Decision 7 — Modular Blueprints**

**What:** Route logic split into 10 blueprints.

| Blueprint | Module | Purpose |
|-----------|--------|---------|
| `auth_bp` | `routes/auth_routes.py` | Login, register, logout |
| `audio_bp` | `routes/audio_routes.py` | Audio upload & processing |
| `pdf_bp` | `routes/pdf_routes.py` | PDF upload & summarization |
| `chat_bp` | `routes/chat_routes.py` | Chat CRUD |
| `rag_bp` | `routes/rag_routes.py` | RAG Q&A |
| `upload_bp` | `routes/upload_routes.py` | Unified file intake |
| `transcript_bp` | `routes/transcript_routes.py` | Transcript retrieval |
| `summary_bp` | `routes/summary_routes.py` | Summary generation |
| `emotion_bp` | `routes/emotion_routes.py` | Emotion analysis |

---

### ✅ **Decision 8 — Frontend Architecture**

**What:** Vanilla JavaScript SPA with Tailwind CSS.

**Key components:**
- Authentication screens (login/register)
- File upload (audio, video, PDF)
- Processing queue with status tracking
- Transcript display with speaker colours
- Emotion visualisation
- Summary display with Markdown rendering
- RAG Q&A with chat history

---

## What Changed from ADR-001

| Decision | ADR-001 | ADR-002 (Final) |
|----------|---------|-----------------|
| **LLM Provider** | Ollama | Groq |
| **ASR Library** | openai-whisper | faster-whisper |
| **Summarisation** | Gemma + T5 + Template | Groq + Template |
| **Authentication** | ❌ None | ✅ Multi-user auth |
| **Data Store** | JSON files | SQLite |
| **Deployment** | Manual/Local | Railway with volumes |

---

## Lessons Learned

### ✅ What Worked Well

| Decision | Why It Worked |
|----------|---------------|
| **SQLite over JSON** | Concurrent writes, schema enforcement, fast queries |
| **Blueprint architecture** | Clean separation of concerns, easy to debug |
| **Service layer pattern** | Business logic decoupled from routes, easy testing |
| **Groq over Ollama** | Faster, better quality, works on Railway |
| **Multi-user auth** | Essential for production, proper data isolation |
| **Session-based auth** | Simpler than JWT for this use case |
| **Environment variables** | Clean configuration, no hardcoded values |

### ⚠️ What Was Challenging

| Challenge | How We Fixed It |
|-----------|-----------------|
| **Memory limits on Railway free tier** | Upgraded to Hobby plan (2GB → 8GB RAM) |
| **T5 causing worker timeouts** | Removed T5 entirely |
| **Pyannote memory usage (~2GB)** | Works on Hobby plan; fallback for lower tiers |
| **OpenAI Whisper build issues** | Switched to faster-whisper |
| **Gemma model download (~4+GB)** | Replaced with Groq API |
| **Ollama not on Railway** | Switched to Groq API |
| **Frontend upload timeouts** | Increased timeout to 300 seconds |

---

## Current Production Stack

| Layer | Technology |
|-------|------------|
| **Backend Framework** | Flask 3.1.0 |
| **Database** | SQLite (WAL mode) |
| **ASR** | faster-whisper 1.0.3 |
| **Diarization** | pyannote.audio 3.1.1 |
| **Emotion Analysis** | DistilBERT + RoBERTa-go_emotions |
| **Summarisation** | Groq API (Llama 3.3 70B) |
| **Embeddings** | sentence-transformers/all-MiniLM-L6-v2 |
| **Vector Search** | FAISS (CPU) |
| **Authentication** | bcrypt + Flask sessions |
| **Frontend** | Vanilla JS + Tailwind CSS |
| **Deployment** | Railway (Docker + Volume) |

---


## Cost Analysis (Railway)

| Plan | Monthly Cost | RAM | Works? |
|------|--------------|-----|--------|
| **Free** | $0 | 512MB - 1GB | ❌ OOM |
| **Hobby** | $5 | 2GB - 48GB | ✅ Yes |
| **Pro** | $20 | 4GB - 1TB | ✅ Yes |

**Recommendation:** Hobby plan ($5/month) is sufficient for this project.

---

## Related Documents

- [README.md](README.md) — Installation and deployment
- [.env.example](.env.example) — Full environment variables list
- [research/README.md](research/README.md) — Research labs guide

---

**This ADR is final — the project is production-ready.** 🚀