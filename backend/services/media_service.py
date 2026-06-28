"""
MediaService — orchestrates the complete video/audio AI pipeline.

Pipeline order (steps 2+3 run in parallel)
-------------------------------------------
1. AudioExtractionService      — extract / convert to 16 kHz mono WAV
2. DiarizationService    ──┐
                            ├── parallel (different models, same WAV)
3. TranscriptionService  ──┘
4. TranscriptAlignmentService  — map words to speakers
5. EmotionService              — sentiment + 28-class emotion per segment

All steps log their stage name and elapsed time.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config.settings import settings
from utils.logging_utils import get_logger
from utils.time_utils import seconds_to_hms

log = get_logger("MediaService")


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class MediaProcessingResult:
    file_id:           str
    status:            str                   = "processed"
    duration:          str                   = "00:00:00"
    duration_seconds:  float                 = 0.0
    full_text:         str                   = ""
    transcript:        List[Dict[str, Any]]  = field(default_factory=list)
    conversation:      List[Dict[str, Any]]  = field(default_factory=list)
    per_speaker:       Dict[str, str]        = field(default_factory=dict)
    speaker_count:     int                   = 0
    emotion_available: bool                  = False
    emotion_analysis:  Optional[dict]        = None
    error:             Optional[str]         = None


# ── Service ───────────────────────────────────────────────────────────────────

class MediaService:
    """Single entry point for processing an uploaded audio/video file."""

    def process(
        self,
        file_id:  str,
        src_path: Path,
        *,
        run_emotion: bool = True,
    ) -> MediaProcessingResult:
        """
        Run the full pipeline on *src_path* and persist results.

        Parameters
        ----------
        file_id     : UUID string for this upload
        src_path    : path to the uploaded file (any audio/video format)
        run_emotion : whether to run emotion analysis (default True)

        Returns
        -------
        MediaProcessingResult with all fields populated.
        Error cases are returned as result.status == "failed", not raised,
        so callers can always jsonify the result.
        """
        output_dir = settings.UPLOAD_FOLDER / file_id
        output_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"processing {src_path.name} ({file_id})")

        result = MediaProcessingResult(file_id=file_id)

        # ── 1. Audio extraction ───────────────────────────────────────────────
        try:
            from services.audio_extraction_service import (
                audio_extraction_service,
                MissingFFmpegError,
                EmptyAudioError,
            )
            wav_path = audio_extraction_service.prepare_wav(src_path, output_dir)
            result.duration_seconds = audio_extraction_service.get_duration(wav_path)
            result.duration         = seconds_to_hms(result.duration_seconds)
            log.info(f"duration: {result.duration}")
        except MissingFFmpegError as exc:
            return self._fail(result, f"ffmpeg not found — {exc}")
        except EmptyAudioError as exc:
            return self._fail(result, f"empty audio — {exc}")
        except Exception as exc:
            return self._fail(result, f"audio extraction failed — {exc}")

        # ── 2 + 3. Diarization & Transcription — run in parallel ─────────────
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_diar:  Future = pool.submit(self._diarize,     wav_path, result.duration_seconds)
            fut_trans: Future = pool.submit(self._transcribe,  wav_path)

            # Collect — _diarize always succeeds (fallback on error),
            # _transcribe returns (ok, result_or_error_msg)
            segments, speaker_segs, speaker_count = fut_diar.result()
            trans_ok, whisper_result               = fut_trans.result()

        if not trans_ok:
            return self._fail(result, f"transcription failed — {whisper_result}")

        result.speaker_count = speaker_count
        log.info(f"diarization: {speaker_count} speaker(s), {len(segments)} segments")
        log.info(f"transcription: {len(whisper_result.get('text', ''))} chars")

        # ── 4. Speaker alignment ──────────────────────────────────────────────
        try:
            from services.transcript_alignment_service import transcript_alignment_service
            full_text, per_speaker, segs_with_text, conversation = (
                transcript_alignment_service.align(whisper_result, speaker_segs)
            )
            result.full_text    = full_text
            result.transcript   = segs_with_text
            result.conversation = conversation
            result.per_speaker  = per_speaker
        except Exception as exc:
            return self._fail(result, f"speaker alignment failed — {exc}")

        # ── 5. Emotion analysis (optional) ────────────────────────────────────
        emotion_data: Optional[dict] = None
        if run_emotion and segs_with_text:
            try:
                from services.emotion_service import emotion_service
                emotion_report = emotion_service.analyze_segments(segs_with_text)
                emotion_data   = {
                    "overall":             emotion_report.overall,
                    "per_speaker_emotion": emotion_report.per_speaker_emotion,
                    "timeline":            emotion_report.timeline,
                }
                result.emotion_analysis  = emotion_data
                result.emotion_available = True
                log.info("emotion analysis complete")
            except Exception as exc:
                log.warn(f"emotion analysis skipped: {exc}")

        # ── Persist ───────────────────────────────────────────────────────────
        self._persist(result, output_dir, segments, emotion_data)

        log.info(f"done: {file_id}")
        return result

    # ── Parallel workers ─────────────────────────────────────────────────────

    @staticmethod
    def _diarize(
        wav_path: Path, duration_seconds: float
    ) -> Tuple[List[dict], Dict[str, list], int]:
        """Run diarization; always returns a result — falls back to single speaker on any error."""
        try:
            from services.diarization_service import diarization_service
            result = diarization_service.diarize(wav_path)
            log.info(f"diarization complete: {result[2]} speakers")
            return result
        except Exception as exc:
            log.warn(f"diarization failed ({exc}), using single-speaker fallback")
            dur = duration_seconds or 600.0
            segs = [{"start": 0.0, "end": dur, "speaker": "SPEAKER_00"}]
            return segs, {"SPEAKER_00": segs}, 1

    @staticmethod
    def _transcribe(wav_path: Path) -> Tuple[bool, Any]:
        """Run transcription; returns (True, whisper_result) or (False, error_message)."""
        try:
            from services.transcription_service import transcription_service
            return True, transcription_service.transcribe(wav_path)
        except Exception as exc:
            return False, str(exc)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _fail(result: MediaProcessingResult, msg: str) -> MediaProcessingResult:
        result.status = "failed"
        result.error  = msg
        log.error(msg)
        return result

    @staticmethod
    def _persist(
        result:      MediaProcessingResult,
        output_dir:  Path,
        raw_segments: List[dict],
        emotion_data: Optional[dict],
    ) -> None:
        """Write transcript.json, transcript.txt, segments.json, etc."""
        payload: Dict[str, Any] = {
            "file_id":       result.file_id,
            "full_text":     result.full_text,
            "conversation":  result.conversation,
            "segments":      raw_segments,
            "segments_with_text": result.transcript,
            "per_speaker":   result.per_speaker,
            "speaker_count": result.speaker_count,
            "duration":      result.duration,
            "duration_seconds": result.duration_seconds,
            "processed_at":  datetime.now().isoformat(),
        }
        if emotion_data:
            payload["emotion_analysis"]   = emotion_data
            payload["segments_with_emotion"] = result.transcript

        (output_dir / "transcript.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (output_dir / "transcript.txt").write_text(
            result.full_text, encoding="utf-8"
        )
        (output_dir / "segments.json").write_text(
            json.dumps(raw_segments, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if emotion_data:
            (output_dir / "emotion_analysis.json").write_text(
                json.dumps(emotion_data, indent=2, ensure_ascii=False), encoding="utf-8"
            )


media_service = MediaService()
