"""
TranscriptionService — speech-to-text via OpenAI Whisper.

Speaker alignment has been moved to TranscriptAlignmentService.
This service focuses solely on running the Whisper model.
"""
from __future__ import annotations

from pathlib import Path

from config.settings import settings
from utils.logging_utils import get_logger

log = get_logger("Transcription")


class TranscriptionService:
    """
    Wraps OpenAI Whisper.  The model is lazy-loaded on first use and cached.

    For speaker-attributed output, pass the result of transcribe() to
    TranscriptAlignmentService.align().
    """

    def __init__(self):
        self._model  = None
        self._device = "cpu"

    # ── Loader ────────────────────────────────────────────────────────────────

    def _load(self):
        if self._model is not None:
            return
        try:
            import whisper
        except ImportError as exc:
            raise ImportError("openai-whisper is required for TranscriptionService") from exc

        from utils.gpu_utils import get_device
        self._device = get_device(settings.TORCH_DEVICE)
        log.info(f"loading whisper {settings.WHISPER_MODEL} on {self._device}…")
        self._model = whisper.load_model(settings.WHISPER_MODEL, device=self._device)
        log.info(f"whisper ready (device={self._device})")

    # ── Core transcription ────────────────────────────────────────────────────

    def transcribe(self, audio_path: Path) -> dict:
        """
        Transcribe *audio_path* and return the raw Whisper result dict.

        Always uses word_timestamps=True so that TranscriptAlignmentService
        can perform accurate word-level speaker attribution.
        fp16 is enabled automatically on CUDA for faster inference.
        """
        self._load()
        log.info(f"transcribing {Path(audio_path).name}…")
        result = self._model.transcribe(
            str(audio_path),
            fp16=(self._device == "cuda"),   # fp16 only on CUDA — crashes on CPU
            word_timestamps=True,
            condition_on_previous_text=False,
        )
        log.info(f"transcribed {len(result.get('text', ''))} chars")
        return result

    # ── Convenience wrapper ───────────────────────────────────────────────────

    def transcribe_and_align(
        self,
        audio_path: Path,
        speaker_segs: dict,
    ) -> tuple:
        """
        Shortcut: transcribe then align in one call.

        Returns the same four-tuple as TranscriptAlignmentService.align().
        """
        from services.transcript_alignment_service import transcript_alignment_service
        whisper_result = self.transcribe(audio_path)
        return transcript_alignment_service.align(whisper_result, speaker_segs)
    

    def process_with_diarization(self, audio_path: str, speaker_segs: dict = None) -> dict:
        """Legacy method for compatibility with existing routes."""
        from services.diarization_service import diarization_service
        from services.transcript_alignment_service import transcript_alignment_service
        
        audio_path = Path(audio_path)
        
        # If no speaker segments provided, run diarization
        if speaker_segs is None:
            segments, speaker_segs, speaker_count = diarization_service.diarize(audio_path)
        
        # Transcribe and align
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


transcription_service = TranscriptionService()
