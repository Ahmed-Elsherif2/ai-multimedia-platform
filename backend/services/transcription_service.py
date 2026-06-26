"""
TranscriptionService — speech-to-text via Faster Whisper.

Uses faster-whisper (CTranslate2) for faster inference with lower memory usage.
Falls back to OpenAI Whisper if faster-whisper is not available.
"""
from __future__ import annotations

from pathlib import Path

from config.settings import settings
from utils.logging_utils import get_logger

log = get_logger("Transcription")


class TranscriptionService:
    """
    Wraps Faster Whisper for fast, memory-efficient transcription.
    
    Falls back to OpenAI Whisper if faster-whisper is not installed.
    The model is lazy-loaded on first use and cached.
    """

    def __init__(self):
        self._model = None
        self._device = "cpu"
        self._compute_type = "int8"  # int8 for CPU, float16 for GPU

    # ── Loader ────────────────────────────────────────────────────────────────

    def _load(self):
        if self._model is not None:
            return
        
        from utils.gpu_utils import get_device
        self._device = get_device(settings.TORCH_DEVICE)
        
        # ⚠️ Force CPU on Windows to avoid OpenMP issues
        import platform
        if platform.system() == "Windows":
            self._device = "cpu"
            self._compute_type = "int8"
        elif self._device == "cuda":
            self._compute_type = "float16"
        else:
            self._compute_type = "int8"
        
        try:
            from faster_whisper import WhisperModel
            log.info(f"loading faster-whisper {settings.WHISPER_MODEL} on {self._device} (compute={self._compute_type})…")
            self._model = WhisperModel(
                settings.WHISPER_MODEL,
                device=self._device,
                compute_type=self._compute_type,
                cpu_threads=4,
                num_workers=2
            )
            log.info(f"faster-whisper ready (device={self._device})")
            self._use_faster_whisper = True
        except ImportError:
            # Fallback to OpenAI Whisper
            import whisper
            self._model = whisper.load_model(settings.WHISPER_MODEL, device=self._device)
            self._use_faster_whisper = False
            log.info(f"OpenAI Whisper ready (device={self._device})")
            return
        
        self._use_faster_whisper = True

    # ── Core transcription ────────────────────────────────────────────────────

    def transcribe(self, audio_path: Path) -> dict:
        """
        Transcribe *audio_path* and return the raw Whisper result dict.
        
        Returns a dict compatible with OpenAI Whisper's output format,
        so TranscriptAlignmentService works without changes.
        """
        self._load()
        log.info(f"transcribing {Path(audio_path).name}…")
        
        if self._use_faster_whisper:
            return self._transcribe_faster(audio_path)
        else:
            return self._transcribe_openai(audio_path)

    def _transcribe_faster(self, audio_path: Path) -> dict:
        """Transcribe using Faster Whisper (CTranslate2)."""
        segments, info = self._model.transcribe(
            str(audio_path),
            beam_size=3,
            language="en",
            word_timestamps=True,
            vad_filter=True,  # Voice Activity Detection filter
            vad_parameters=dict(
                threshold=0.5,
                min_speech_duration_ms=250,
                min_silence_duration_ms=100,
            ),
        )
        
        # Convert to OpenAI Whisper format for compatibility
        segments_list = []
        full_text = []
        
        for seg in segments:
            seg_dict = {
                "id": len(segments_list),
                "seek": 0,
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "tokens": [],
                "temperature": 0.0,
                "avg_logprob": -0.2,
                "compression_ratio": 1.0,
                "no_speech_prob": 0.0,
            }
            
            # Add word-level timestamps if available
            if hasattr(seg, 'words') and seg.words:
                seg_dict["words"] = [
                    {"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                    for w in seg.words
                ]
            else:
                # Fallback: no word timestamps
                seg_dict["words"] = []
            
            segments_list.append(seg_dict)
            full_text.append(seg.text)
        
        return {
            "text": " ".join(full_text).strip(),
            "segments": segments_list,
            "language": "en",
        }

    def _transcribe_openai(self, audio_path: Path) -> dict:
        """Transcribe using OpenAI Whisper (fallback)."""
        import whisper
        result = self._model.transcribe(
            str(audio_path),
            fp16=(self._device == "cuda"),
            word_timestamps=True,
            condition_on_previous_text=False,
        )
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


transcription_service = TranscriptionService()