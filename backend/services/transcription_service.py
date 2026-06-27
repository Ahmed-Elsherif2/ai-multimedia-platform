"""
TranscriptionService — speech-to-text via Groq Whisper API.

Uses Groq's hosted Whisper API (whisper-large-v3-turbo) for fast,
accurate transcription without local model loading.
"""
from __future__ import annotations

import os
from pathlib import Path

from config.settings import settings
from utils.logging_utils import get_logger

log = get_logger("Transcription")


class TranscriptionService:
    """
    Wraps Groq's Whisper API for fast, cloud-based transcription.
    
    No local model loading – uses Groq's enterprise GPUs.
    Free tier: 2,000 requests/day, 20 requests/minute.
    """

    def __init__(self):
        self._client = None

    def _load(self):
        """Lazy load the Groq client."""
        if self._client is not None:
            return
        
        from groq import Groq
        
        api_key = settings.GROQ_API_KEY
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY not set. Get one from: https://console.groq.com/keys\n"
                "Free tier: 2,000 requests/day, 20 requests/minute."
            )
        
        self._client = Groq(api_key=api_key)
        log.info("Groq Whisper API client ready")

    def transcribe(self, audio_path: Path) -> dict:
        """
        Transcribe audio using Groq's hosted Whisper API.
        
        Returns a dict compatible with OpenAI Whisper's output format.
        """
        self._load()
        audio_path = Path(audio_path)
        log.info(f"transcribing {audio_path.name} via Groq Whisper API...")

        try:
            with open(audio_path, "rb") as file:
                transcription = self._client.audio.transcriptions.create(
                    file=(audio_path.name, file.read()),
                    model="whisper-large-v3-turbo",  # Fastest model
                    response_format="verbose_json",   # Returns timestamps
                    language="en",
                )
            
            # Convert to OpenAI-compatible format for alignment
            result = {
                "text": transcription.text,
                "segments": [],
                "language": getattr(transcription, "language", "en"),
            }
            
            # Convert segments to OpenAI format
            if hasattr(transcription, "segments") and transcription.segments:
                for i, seg in enumerate(transcription.segments):
                    result["segments"].append({
                        "id": i,
                        "start": seg.start,
                        "end": seg.end,
                        "text": seg.text,
                        "words": [],
                    })
            else:
                # Fallback: treat entire text as one segment
                result["segments"] = [{
                    "id": 0,
                    "start": 0.0,
                    "end": 0.0,
                    "text": transcription.text,
                    "words": [],
                }]
            
            log.info(f"transcription complete: {len(result['text'])} chars")
            return result

        except Exception as exc:
            log.error(f"Groq API error: {exc}")
            raise RuntimeError(f"Transcription failed: {exc}")

    def transcribe_and_align(
        self,
        audio_path: Path,
        speaker_segs: dict,
    ) -> tuple:
        """
        Shortcut: transcribe then align in one call.
        """
        from services.transcript_alignment_service import transcript_alignment_service
        whisper_result = self.transcribe(audio_path)
        return transcript_alignment_service.align(whisper_result, speaker_segs)

    def process_with_diarization(self, audio_path: str, speaker_segs: dict = None) -> dict:
        """Legacy method for compatibility with existing routes."""
        from services.diarization_service import diarization_service
        from services.transcript_alignment_service import transcript_alignment_service
        
        audio_path = Path(audio_path)
        
        if speaker_segs is None:
            segments, speaker_segs, speaker_count = diarization_service.diarize(audio_path)
        
        whisper_result = self.transcribe(audio_path)
        full_text, per_speaker, segments_with_text, conversation = (
            transcript_alignment_service.align(whisper_result, speaker_segs)
        )
        
        return {
            "full_text": full_text,
            "segments": segments_with_text,
            "conversation": conversation,
            "per_speaker": per_speaker,
            "speaker_count": len(per_speaker)
        }


# Module-level singleton
transcription_service = TranscriptionService()