FROM python:3.11.7

# Install ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY . .

RUN mkdir -p /app/data/uploads /app/data/results /app/data/status

# ── Set Hugging Face cache to volume ──
ENV HF_HOME=/root/.cache/huggingface
ENV TRANSFORMERS_CACHE=/root/.cache/huggingface
ENV HUGGINGFACE_HUB_CACHE=/root/.cache/huggingface

# ── Preload models during build ──
RUN echo "🚀 Preloading models during Docker build..." && \
    python backend/preload.py

ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/app/data

EXPOSE 5000
CMD cd backend && gunicorn -w 4 -b 0.0.0.0:$PORT app:app