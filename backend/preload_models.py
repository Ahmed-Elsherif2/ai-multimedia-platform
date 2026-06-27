"""
Preload all AI models during Docker build.
This script is called during the Docker build process.
"""
import os
import sys

sys.path.insert(0, '/app/backend')

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

from config.settings import settings

print("==========================================")
print("🚀 Preloading AI models during Docker build...")
print("==========================================")

# 1. Preload Emotion models
print('📊 Loading Emotion models...')
try:
    from services.emotion_service import emotion_service
    emotion_service.analyze_segment('warmup')
    print('✅ Emotion models loaded')
except Exception as e:
    print(f'⚠️ Emotion warmup failed: {e}')

# 2. Preload Pyannote (HEAVY - 1.5GB download)
print('🎙️ Loading Pyannote diarization...')
try:
    from services.diarization_service import diarization_service
    diarization_service._load()
    print('✅ Pyannote loaded')
except Exception as e:
    print(f'⚠️ Pyannote load failed: {e}')

# 3. Preload RAG embedder (Sentence-Transformers)
print('🧠 Loading RAG embedding model...')
try:
    from services.rag_service import rag_service
    rag_service._get_embedder()
    print('✅ RAG embedder loaded')
except Exception as e:
    print(f'⚠️ RAG embedder failed: {e}')

# 4. Verify API keys
if settings.GROQ_API_KEY:
    print('✅ Groq API configured')
else:
    print('⚠️ GROQ_API_KEY not set - summarization/RAG will fail')

if settings.HF_TOKEN:
    print('✅ HF_TOKEN configured')
else:
    print('⚠️ HF_TOKEN not set - diarization will fail')

print('✅ All models preloaded during build!')