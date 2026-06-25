# How to Run Locally — Step by Step

---

## What you need to install once

| Tool | Why | Download |
| ---- | --- | -------- |
| Python 3.11 | Run the backend | <https://www.python.org/downloads/> |
| ffmpeg | Convert audio/video to WAV | <https://ffmpeg.org/download.html> — add to PATH |
| Ollama | Local LLM for chat/RAG | <https://ollama.com/download> |

> **ffmpeg on Windows**: download the "essentials" build, extract it, and add
> the `bin/` folder to your System PATH. Open a new terminal and type
> `ffmpeg -version` to confirm it works.

---

## 1 — First-time setup (do this once)

### 1a. Create a Python virtual environment

```powershell
python -m venv .venv
.venv\Scripts\activate
```

You will see `(.venv)` at the start of the prompt. **Always activate it before running the app.**

### 1b. Install Python dependencies

**CPU (default — works on any machine):**

```powershell
pip install -r backend/requirements.txt
```

**NVIDIA GPU (faster — Whisper, Pyannote, and emotion models run on CUDA):**

```powershell
pip install -r backend/requirements.txt
pip install -r backend/requirements-cuda.txt
```

> Run `nvidia-smi` first to confirm your driver and CUDA version.
> `requirements-cuda.txt` targets CUDA 11.8 — works on 12.x cards too.
> After installing, set `TORCH_DEVICE=cuda` in `.env` to force GPU use,
> or leave it as `auto` to detect automatically.

**Gemma (optional)**: if you want PDF summarization with Gemma, also run:

```powershell
# CPU build:
pip install llama-cpp-python
# GPU build (CUDA):
$env:CMAKE_ARGS="-DLLAMA_CUDA=on"; pip install llama-cpp-python
```

### 1c. Get a HuggingFace token

1. Go to <https://huggingface.co/settings/tokens> and create a **Read** token.
2. Accept the model terms for **both** of these (required for speaker diarization):
   - <https://huggingface.co/pyannote/speaker-diarization-3.1> → click **Agree**
   - <https://huggingface.co/pyannote/segmentation-3.0> → click **Agree**

> **If you skip this**: the app still runs and transcribes correctly, but all speech
> is attributed to a single speaker (SPEAKER\_00) instead of being separated by person.

### 1d. Create your .env file

```powershell
copy .env.example .env
```

Open `.env` and fill in:

```text
HF_TOKEN=hf_your_token_here
```

Everything else has working defaults. See `.env.example` for all options.

### 1e. Pull the Ollama model

```powershell
ollama pull llama3.2
```

---

## 2 — Running the app (every time)

You need **two terminals**:

### Terminal 1 — Ollama

```powershell
ollama serve
```

Leave this running. Ollama listens on `http://localhost:11434`.

### Terminal 2 — Flask backend

```powershell
.venv\Scripts\activate
python backend/app.py
```

Open your browser at **<http://localhost:5000>**

The frontend is served automatically by Flask — no separate frontend server needed.

---

## 3 — Gemma model (PDF summarization)

The Gemma GGUF model (~3.5 GB) must be downloaded manually.

**Step 1** — Download the file:

- Go to <https://huggingface.co/google/gemma-4-E4B-it-GGUF>
- Download `gemma-4-E4B-it-Q4_K_M.gguf`
- Save it anywhere, e.g. `C:\Users\YourName\models\gemma-4-E4B-it-Q4_K_M.gguf`

**Step 2** — Set the path in `.env`:

```text
GEMMA_MODEL_PATH=C:\Users\YourName\models\gemma-4-E4B-it-Q4_K_M.gguf
```

> **If you skip this**: the app still works — PDF summarization falls back to the
> template extractor automatically. No crash.

---

## 4 — Where is data stored?

All metadata, transcripts, summaries, and chat history are stored in a
**SQLite database** that is created automatically on first run:

```text
backend/
  data/
    platform.db       ← SQLite database (files, transcripts, summaries, chats)
  uploads/
    <file_id>/
      original.*      ← your uploaded audio/video/pdf (binary, stays on disk)
      audio.wav       ← extracted audio used for transcription
      transcript.json ← on-disk copy kept in sync with the database
```

- The database and upload folder are created automatically on first run.
- Deleting `backend/data/platform.db` resets all metadata (transcripts, chats, summaries).
- Deleting `backend/uploads/` removes the original files from disk.
- Both are excluded from git via `.gitignore`.

AI models (Whisper, Pyannote, emotion models) are downloaded automatically
from HuggingFace the **first time** you process a file. They are cached in
`~/.cache/huggingface/` — not inside this project folder.

---

## 5 — Uploading files

| File type | What happens on upload |
| --------- | ---------------------- |
| **Video** (`.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`) | Full pipeline runs automatically — diarization → transcription → emotion analysis. Transcript is ready when the upload finishes (~1–5 min depending on length). No extra click needed. |
| **Audio** (`.mp3`, `.wav`, `.flac`, `.m4a`, `.ogg`) | File is saved. Click **Process Content** to start the pipeline. |
| **PDF** | File is saved. Click **Process Content** to run summarization. |

> Re-uploading a file with the same name in the same chat replaces the previous
> entry — no duplicates.

---

## 6 — Quick-start checklist

```text
[ ] Python 3.11 installed
[ ] ffmpeg installed and on PATH       (test: ffmpeg -version)
[ ] Ollama installed and running       (test: ollama list)
[ ] .venv created and activated
[ ] pip install -r backend/requirements.txt  done
[ ] .env file created with HF_TOKEN filled in
[ ] Accepted pyannote/speaker-diarization-3.1 terms on HuggingFace
[ ] Accepted pyannote/segmentation-3.0 terms on HuggingFace
[ ] ollama pull llama3.2  done
[ ] python backend/app.py  running
[ ] Browser open at http://localhost:5000
```
