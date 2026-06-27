FROM python:3.11.7

# Install ffmpeg for audio processing
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first (for better caching)
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy the rest of the application
COPY . .

# Create data directory
RUN mkdir -p /app/data/uploads /app/data/results /app/data/status

# ──────────────────────────────────────────────────────────────
# 🚀 PRELOAD ALL MODELS DURING BUILD (using the script)
# ──────────────────────────────────────────────────────────────
RUN python backend/preload_models.py

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/app/data

# Expose port
EXPOSE 5000

# Start with gunicorn
CMD cd backend && gunicorn -w 4 -b 0.0.0.0:$PORT app:app