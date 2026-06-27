#!/usr/bin/env python
"""
Preload all AI models – run this ONCE from the Railway console.
This will download models to /root/.cache/huggingface (your volume).
After this, all subsequent requests will be fast.

How to run:
    cd /app/backend
    python preload_console.py
"""
import os
import sys
import time

# Add backend to path
sys.path.insert(0, '/app/backend')

print("=" * 60)
print("🚀 PRELOADING MODELS – RUNNING ON RAILWAY CONSOLE")
print("=" * 60)

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

from config.settings import settings

print(f"📁 Data directory: {settings.DATA_DIR}")
print(f"📁 HF_TOKEN set: {'✅' if settings.HF_TOKEN else '❌'}")
print(f"📁 GROQ_API_KEY set: {'✅' if settings.GROQ_API_KEY else '❌'}")
print("")

# ── 1. Emotion models ──
print("📊 Loading Emotion models (DistilBERT + RoBERTa-go_emotions)...")
start = time.time()
try:
    from services.emotion_service import emotion_service
    emotion_service.analyze_segment("warmup")
    print(f"✅ Emotion models loaded in {time.time() - start:.1f}s")
except Exception as e:
    print(f"⚠️ Emotion failed: {e}")

# ── 2. Pyannote (HEAVY) ──
print("🎙️ Loading Pyannote diarization (this takes 2-3 minutes)...")
start = time.time()
try:
    from services.diarization_service import diarization_service
    diarization_service._load()
    print(f"✅ Pyannote loaded in {time.time() - start:.1f}s")
except Exception as e:
    print(f"⚠️ Pyannote failed: {e}")

# ── 3. RAG embedder ──
print("🧠 Loading RAG embedding model (sentence-transformers)...")
start = time.time()
try:
    from services.rag_service import rag_service
    rag_service._get_embedder()
    print(f"✅ RAG embedder loaded in {time.time() - start:.1f}s")
except Exception as e:
    print(f"⚠️ RAG embedder failed: {e}")

print("")
print("=" * 60)
print("✅ All models preloaded!")
print("📁 Models saved to: /root/.cache/huggingface")
print("🔄 This volume will persist across restarts and deployments")
print("=" * 60)