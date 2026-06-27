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
import subprocess
import threading

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


# ── Helper: Monitor HuggingFace cache folder size ──
def get_folder_size(path):
    """Get size of a folder in MB."""
    total = 0
    if not os.path.exists(path):
        return 0
    try:
        for entry in os.scandir(path):
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_folder_size(entry.path)
    except:
        pass
    return total / (1024 * 1024)  # MB


def monitor_cache_size(stop_event):
    """Background thread to show cache size every 5 seconds."""
    cache_path = "/root/.cache/huggingface"
    last_size = 0
    while not stop_event.is_set():
        time.sleep(5)
        try:
            size_mb = get_folder_size(cache_path)
            if size_mb > last_size + 10:  # Only show if increased by >10MB
                print(f"   📦 Cache size: {size_mb:.1f} MB (downloading...)")
                last_size = size_mb
        except:
            pass


# ── 1. Emotion models ──
print("📊 Loading Emotion models (DistilBERT + RoBERTa-go_emotions)...")
start = time.time()
try:
    from services.emotion_service import emotion_service
    emotion_service.analyze_segment("warmup")
    print(f"✅ Emotion models loaded in {time.time() - start:.1f}s")
except Exception as e:
    print(f"⚠️ Emotion failed: {e}")

# ── 2. Pyannote (HEAVY) with progress monitor ──
print("🎙️ Loading Pyannote diarization (this takes 2-3 minutes)...")
print("   ⏳ Downloading pyannote/speaker-diarization-3.1 (~1.5GB)")
print("   📦 This will be saved to your volume permanently")
print("")

# Start background monitor
stop_monitor = threading.Event()
monitor_thread = threading.Thread(target=monitor_cache_size, args=(stop_monitor,))
monitor_thread.daemon = True
monitor_thread.start()

start = time.time()
try:
    from services.diarization_service import diarization_service
    diarization_service._load()
    elapsed = time.time() - start
    print("")
    print(f"✅ Pyannote loaded in {elapsed:.1f}s")
    
    # Show final cache size
    cache_path = "/root/.cache/huggingface"
    if os.path.exists(cache_path):
        size_mb = get_folder_size(cache_path)
        print(f"   📦 Total cache size: {size_mb:.1f} MB")
except Exception as e:
    print(f"⚠️ Pyannote failed: {e}")
finally:
    stop_monitor.set()
    monitor_thread.join(timeout=2)

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

# Show final cache size
cache_path = "/root/.cache/huggingface"
if os.path.exists(cache_path):
    size_mb = get_folder_size(cache_path)
    print(f"📦 Final cache size: {size_mb:.1f} MB")
    if size_mb > 100:
        print("✅ Models successfully downloaded to volume!")
    else:
        print("⚠️ Cache size is small - models may not have downloaded fully")
print("=" * 60)