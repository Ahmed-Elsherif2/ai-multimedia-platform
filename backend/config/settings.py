"""
Central application configuration.

Every value is sourced from an environment variable with a safe default.
No hardcoded paths, credentials, or developer-specific values live here.
Load a .env file (see .env.example at the project root) for local development.

Hosting Compatible: All paths use environment variables.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Set Hugging Face cache directory ──
HF_CACHE = os.getenv("HF_HOME", "/root/.cache/huggingface")
os.environ["HF_HOME"] = HF_CACHE
os.environ["TRANSFORMERS_CACHE"] = HF_CACHE
os.environ["HUGGINGFACE_HUB_CACHE"] = HF_CACHE

class Settings:
    # ── Base Directories ──────────────────────────────────────────────────────
    BASE_DIR: Path = Path(os.getenv("BASE_DIR", str(Path(__file__).resolve().parent.parent)))
    
    # ── Storage ──────────────────────────────────────────────────────────────
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
    UPLOAD_FOLDER: Path = Path(os.getenv("UPLOAD_FOLDER", str(DATA_DIR / "uploads")))
    RESULTS_FOLDER: Path = Path(os.getenv("RESULTS_FOLDER", str(DATA_DIR / "results")))
    STATUS_FOLDER: Path = Path(os.getenv("STATUS_FOLDER", str(DATA_DIR / "status")))
    
    # ── Database ─────────────────────────────────────────────────────────────
    DB_PATH: Path = Path(os.getenv("DB_PATH", str(DATA_DIR / "platform.db")))
    DB_NAME: str = os.getenv("DB_NAME", "platform.db")
    
    # ── Flask ────────────────────────────────────────────────────────────────
    PORT: int = int(os.getenv("PORT", "5000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
    MAX_CONTENT_MB: int = int(os.getenv("MAX_CONTENT_MB", "500"))
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")  # production | development
    
    # ── User ─────────────────────────────────────────────────────────────────
    DEFAULT_USER: str = os.getenv("DEFAULT_USER", "default_user")  # fallback for single-user mode

    # ── Hugging Face ──────────────────────────────────────────────────────────
    HF_TOKEN: str = os.getenv("HF_TOKEN", "")  # required for pyannote diarization

    # ── GROQ API (Primary LLM) ──────────────────────────────────────────────
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    # ── GPU / Device ────────────────────────────────────────────────────────
    TORCH_DEVICE: str = os.getenv("TORCH_DEVICE", "auto")  # auto | cuda | cpu

    # ── ASR (Speech‑to‑Text) ──────────────────────────────────────────────────
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")  # tiny|base|small|medium|large

    # ── Speaker Diarization ──────────────────────────────────────────────────
    PYANNOTE_MODEL: str = os.getenv("PYANNOTE_MODEL", "pyannote/speaker-diarization-3.1")

    # ── Embeddings & RAG ─────────────────────────────────────────────────────
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "6"))
    RAG_CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE", "800"))

    def __init__(self):
        """Create all required directories."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
        self.RESULTS_FOLDER.mkdir(parents=True, exist_ok=True)
        self.STATUS_FOLDER.mkdir(parents=True, exist_ok=True)
        
        # Print relevant configuration on startup
        print(f"[Settings] Environment: {self.ENVIRONMENT}")
        print(f"[Settings] Data directory: {self.DATA_DIR}")
        print(f"[Settings] Database: {self.DB_PATH}")
        print(f"[Settings] Upload folder: {self.UPLOAD_FOLDER}")
        print(f"[Settings] Groq API: {'✅ Configured' if self.GROQ_API_KEY else '❌ Not configured'}")
        print(f"[Settings] HF token: {'✅ Set' if self.HF_TOKEN else '❌ Not set'}")

    @property
    def max_content_length(self) -> int:
        return self.MAX_CONTENT_MB * 1024 * 1024
    
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"
    
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


settings = Settings()