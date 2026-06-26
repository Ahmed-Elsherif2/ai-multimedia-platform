"""
Typed response schemas for the AI Multimedia Platform API.

All public dataclasses have a .to_dict() method so Flask routes can call
jsonify(schema.to_dict()) without additional boilerplate.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ── Transcript ────────────────────────────────────────────────────────────────

@dataclass
class TranscriptSegment:
    start:   float
    end:     float
    speaker: str
    text:    str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TranscriptResponse:
    file_id:       str
    full_text:     str
    segments:      List[Dict[str, Any]]       = field(default_factory=list)
    conversation:  List[Dict[str, Any]]       = field(default_factory=list)
    per_speaker:   Dict[str, str]             = field(default_factory=dict)
    speaker_count: int                        = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Video upload  ───────────────────────────────

@dataclass
class VideoUploadResponse:
    file_id:           str
    status:            str                        = "processed"
    duration:          str                        = "00:00:00"
    duration_seconds:  float                      = 0.0
    transcript:        List[Dict[str, Any]]       = field(default_factory=list)
    conversation:      List[Dict[str, Any]]       = field(default_factory=list)
    full_text:         str                        = ""
    per_speaker:       Dict[str, str]             = field(default_factory=dict)
    speaker_count:     int                        = 0
    emotion_available: bool                       = False
    summary_available: bool                       = False
    rag_available:     bool                       = True
    error:             Optional[str]              = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Emotion ───────────────────────────────────────────────────────────────────

@dataclass
class EmotionResponse:
    file_id:          str
    sentiment:        Dict[str, Any]        = field(default_factory=dict)
    emotion:          Dict[str, Any]        = field(default_factory=dict)
    top_3_emotions:   List[Dict[str, Any]]  = field(default_factory=list)
    timeline:         List[Dict[str, Any]]  = field(default_factory=list)
    per_speaker:      Dict[str, Any]        = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Summarization ─────────────────────────────────────────────────────────────

@dataclass
class SummaryResponse:
    file_id:             str
    full_text_preview:   str   = ""
    full_text_length:    int   = 0
    groq:                str   = ""      # ✅ Primary
    template:            str   = ""
    compression_ratio:   float = 0.0
    model_used:          str   = "template"
    summary_length:      int   = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Upload ────────────────────────────────────────────────────────────────────

@dataclass
class UploadResponse:
    file_id:  str
    filename: str
    type:     str   = "audio"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── RAG ───────────────────────────────────────────────────────────────────────

@dataclass
class RAGResponse:
    answer:  str
    sources: List[Any] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
