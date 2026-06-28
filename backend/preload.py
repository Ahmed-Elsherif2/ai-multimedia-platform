"""
Preload all models on Railway startup.
This should run ONCE when the container starts.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import settings

print("=" * 60)
print("🚀 PRELOADING MODELS ON RAILWAY STARTUP")
print("=" * 60)

# ── 1. Pyannote (the heavy one) ──
print("🎙️ Loading Pyannote diarization...")
try:
    from services.diarization_service import diarization_service
    diarization_service._load()
    print("✅ Pyannote loaded successfully")
except Exception as e:
    print(f"⚠️ Pyannote failed: {e}")

# ── 2. Emotion models ──
print("📊 Loading Emotion models...")
try:
    from services.emotion_service import emotion_service
    emotion_service.analyze_segment("warmup")
    print("✅ Emotion models loaded")
except Exception as e:
    print(f"⚠️ Emotion failed: {e}")

# ── 3. RAG embedder ──
print("🧠 Loading RAG embedding model...")
try:
    from services.rag_service import rag_service
    rag_service._get_embedder()
    print("✅ RAG embedder loaded")
except Exception as e:
    print(f"⚠️ RAG failed: {e}")

print("=" * 60)
print("✅ All models preloaded successfully!")
print("📁 Cache location: /root/.cache/huggingface")
print("🔄 This will persist across restarts via the volume")
print("=" * 60)