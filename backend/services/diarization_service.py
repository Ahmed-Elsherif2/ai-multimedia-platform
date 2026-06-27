"""
DiarizationService — speaker diarization via Pyannote Audio.

Audio extraction (convert_to_wav, get_duration) has been moved to
AudioExtractionService.  This service focuses solely on diarization.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.settings import settings
from utils.logging_utils import get_logger

log = get_logger("Diarization")


class DiarizationService:
    """
    Wraps pyannote/speaker-diarization-3.1 (model set via PYANNOTE_MODEL).

    The pipeline is lazy-loaded on first use and cached for the process
    lifetime — loading it involves a ~2 GB download on first run.
    """

    def __init__(self):
        self._pipeline = None

    # ── Loader ────────────────────────────────────────────────────────────────

    def _load(self):
        if self._pipeline is not None:
            return
        try:
            from pyannote.audio import Pipeline as PyannotePipeline
        except ImportError as exc:
            raise ImportError("pyannote.audio is required for DiarizationService") from exc

        token = settings.HF_TOKEN
        if not token:
            raise RuntimeError(
                "HF_TOKEN environment variable is not set. "
                "A Hugging Face access token is required to download the "
                "pyannote diarization model — see .env.example."
            )

        p = PyannotePipeline.from_pretrained(settings.PYANNOTE_MODEL, use_auth_token=token)
        if not callable(p):
            raise RuntimeError("Pyannote returned a non-callable object — check PYANNOTE_MODEL.")

        from utils.gpu_utils import torch_device
        device = torch_device(settings.TORCH_DEVICE)
        p = p.to(device)
        log.info(f"loaded {settings.PYANNOTE_MODEL} on {device}")
        self._pipeline = p

    # ── Core diarization ─────────────────────────────────────────────────────

    def diarize(
        self, audio_path: Path
    ) -> Tuple[List[dict], Dict[str, List[dict]], int]:
        """
        Run speaker diarization on *audio_path*.

        The input must be a WAV file; use AudioExtractionService.prepare_wav()
        to convert other formats first.

        Returns
        -------
        segments      : time-ordered list of {start, end, speaker}
        speaker_segs  : mapping speaker_label → [segment, …]
        speaker_count : number of distinct speakers
        """
        audio_path = Path(audio_path)

        """
        # ── Get audio duration for short audio fallback ─────────────────────
        from services.audio_extraction_service import audio_extraction_service
        duration = audio_extraction_service.get_duration(audio_path)

        # ── Skip diarization for very short audio (< 16 seconds) ───────────
        if duration < 16:
            log.info(f"short audio ({duration:.1f}s) — using single-speaker fallback")
            fallback = [{"start": 0.0, "end": round(duration, 2), "speaker": "SPEAKER_00"}]
            return fallback, {"SPEAKER_00": fallback}, 1
        """

        # If a non-WAV is passed, try an in-place conversion as a convenience
        wav_path: Optional[Path] = None
        if audio_path.suffix.lower() in {".mp4", ".mp3", ".m4a", ".mov", ".avi", ".mkv", ".webm"}:
            existing = audio_path.with_suffix(".wav")
            if existing.exists():
                audio_path = existing
            else:
                try:
                    wav_path = audio_extraction_service.extract_to_wav(audio_path)
                    audio_path = wav_path
                except Exception as exc:
                    log.warn(f"WAV conversion failed ({exc}) — using original file")

        segments: List[dict] = []
        speaker_segs: Dict[str, List] = {}

        try:
            self._load()
            diarization = self._pipeline(str(audio_path))
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                seg = {"start": round(turn.start, 2), "end": round(turn.end, 2), "speaker": speaker}
                segments.append(seg)
                speaker_segs.setdefault(speaker, []).append(seg)
            log.info(f"{len(speaker_segs)} speaker(s), {len(segments)} segments")
        except Exception as exc:
            log.warn(f"diarization failed ({exc}) — single-speaker fallback")

        # Single-speaker fallback
        if not speaker_segs:
            fallback = [{"start": 0.0, "end": round(duration, 2), "speaker": "SPEAKER_00"}]
            segments = fallback
            speaker_segs = {"SPEAKER_00": fallback}

        # Clean up temp WAV created only for diarization
        if wav_path and wav_path.exists() and wav_path != Path(audio_path):
            try:
                os.remove(wav_path)
            except OSError:
                pass

        return segments, speaker_segs, len(speaker_segs)


diarization_service = DiarizationService()