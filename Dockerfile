FROM python:3.11.7

# ── Build arguments (passed from Railway) ──
ARG HF_TOKEN
ARG GROQ_API_KEY

# Install ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY . .

RUN mkdir -p /app/data/uploads /app/data/results /app/data/status

# ── Set build-time environment variables ──
ENV HF_TOKEN=${HF_TOKEN}
ENV GROQ_API_KEY=${GROQ_API_KEY}

# ── Preload models ──
RUN python backend/preload_models.py

ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/app/data

EXPOSE 5000
CMD cd backend && gunicorn -w 4 -b 0.0.0.0:$PORT app:app