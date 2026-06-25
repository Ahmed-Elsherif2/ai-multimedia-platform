"""
AudioExtractionService — ffmpeg-based audio extraction and WAV conversion.

Extracted from DiarizationService so that audio extraction is independently
testable and can be reused by MediaService without importing pyannote.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from utils.logging_utils import get_logger

log = get_logger("AudioExtraction")


class MissingFFmpegError(RuntimeError):
    """Raised when ffmpeg / ffprobe is not found on PATH."""


class EmptyAudioError(ValueError):
    """Raised when the input file contains no usable audio track."""


class AudioExtractionService:
    """Convert any audio/video file to a 16 kHz mono WAV suitable for Whisper
    and Pyannote, and measure its duration."""

    # ── WAV conversion ────────────────────────────────────────────────────────

    @staticmethod
    def extract_to_wav(input_path: Path, output_path: Optional[Path] = None) -> Path:
        """
        Convert *input_path* to 16 kHz mono WAV.

        Parameters
        ----------
        input_path  : source audio or video file
        output_path : destination WAV path (default: same stem, .wav suffix)

        Returns
        -------
        Path to the produced WAV file.

        Raises
        ------
        MissingFFmpegError  if ffmpeg is not on PATH
        EmptyAudioError     if ffmpeg reports no audio stream
        RuntimeError        on any other ffmpeg failure
        """
        input_path = Path(input_path)
        if output_path is None:
            output_path = input_path.with_suffix(".wav")

        if input_path.suffix.lower() == ".wav" and input_path == output_path:
            return output_path

        log.info(f"extracting audio: {input_path.name} → {output_path.name}")
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", str(input_path),
                    "-acodec", "pcm_s16le",
                    "-ar",     "16000",
                    "-ac",     "1",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise MissingFFmpegError(
                "ffmpeg is not installed or not on PATH. "
                "Install it from https://ffmpeg.org/download.html and add it to PATH."
            )

        if result.returncode != 0:
            stderr = result.stderr
            if "no audio" in stderr.lower() or "invalid data" in stderr.lower():
                raise EmptyAudioError(
                    f"No usable audio track found in '{input_path.name}'."
                )
            raise RuntimeError(
                f"ffmpeg failed (exit {result.returncode}): {stderr[:400]}"
            )

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise EmptyAudioError(
                f"ffmpeg produced an empty WAV file from '{input_path.name}'."
            )

        log.info(f"WAV written ({output_path.stat().st_size // 1024} KB)")
        return output_path

    # ── Duration ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_duration(audio_path: Path) -> float:
        """
        Return audio duration in seconds.

        Uses ffprobe as primary source with librosa as fallback.
        Returns 0.0 if both fail.
        """
        audio_path = Path(audio_path)
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(audio_path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return float(result.stdout.strip())
        except FileNotFoundError:
            log.warn("ffprobe not found — falling back to librosa")
        except Exception as exc:
            log.warn(f"ffprobe failed ({exc}) — falling back to librosa")

        try:
            import librosa
            return float(librosa.get_duration(filename=str(audio_path)))
        except Exception as exc:
            log.warn(f"librosa fallback failed: {exc}")

        return 0.0

    # ── Convenience wrapper ───────────────────────────────────────────────────

    def prepare_wav(self, source_path: Path, output_dir: Path) -> Path:
        """
        Ensure a WAV file exists in *output_dir* for *source_path*.

        If the source is already a WAV at the right location it is returned
        as-is.  Otherwise audio is extracted via ffmpeg.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        wav_dest = output_dir / (source_path.stem + ".wav")

        if source_path.suffix.lower() == ".wav":
            if source_path == wav_dest:
                return source_path
            import shutil
            shutil.copy2(source_path, wav_dest)
            return wav_dest

        return self.extract_to_wav(source_path, wav_dest)


audio_extraction_service = AudioExtractionService()
