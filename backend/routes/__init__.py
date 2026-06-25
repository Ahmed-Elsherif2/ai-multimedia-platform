"""
Routes blueprint registration for the AI Multimedia Platform.
"""
from .audio_routes import audio_bp
from .pdf_routes import pdf_bp
from .chat_routes import chat_bp
from .rag_routes import rag_bp
from .emotion_routes import emotion_bp
from .summary_routes import summary_bp
from .transcript_routes import transcript_bp
from .upload_routes import upload_bp

# For backward compatibility
from .audio_routes import audio_bp as audio_bp_legacy
from .pdf_routes import pdf_bp as pdf_bp_legacy

__all__ = [
    "audio_bp",
    "pdf_bp",
    "chat_bp",
    "rag_bp",
    "emotion_bp",
    "summary_bp",
    "transcript_bp",
    "upload_bp",
    # Legacy aliases
    "audio_bp_legacy",
    "pdf_bp_legacy",
]