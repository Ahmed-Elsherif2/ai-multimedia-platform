"""
TranscriptAlignmentService — maps Whisper words to pyannote speaker segments.

Extracted from TranscriptionService so the alignment logic is independently
testable and can be composed by MediaService without loading Whisper again.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from utils.logging_utils import get_logger

log = get_logger("TranscriptAlignment")


class TranscriptAlignmentService:
    """
    Aligns a raw Whisper result (with word timestamps) to pyannote diarization
    segments at word level, then assembles per-speaker text and conversation turns.
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def align(
        self,
        whisper_result: dict,
        speaker_segs: Dict[str, List[dict]],
    ) -> Tuple[str, Dict[str, str], List[dict], List[dict]]:
        """
        Align Whisper output to diarization segments.

        Parameters
        ----------
        whisper_result : raw dict returned by ``whisper.model.transcribe()``
        speaker_segs   : ``{speaker_label: [{start, end, speaker}, ...]}``

        Returns
        -------
        full_text          : complete transcript string
        per_speaker_joined : ``{speaker: joined text}``
        segments_with_text : ``[{start, end, text, speaker}, ...]``
        conversation       : merged same-speaker dialogue turns
        """
        full_text = whisper_result.get("text", "").strip()

        # Flat time-sorted speaker timeline for O(n) lookup
        timeline = sorted(
            [
                {"start": s["start"], "end": s["end"], "speaker": sp}
                for sp, segs in speaker_segs.items()
                for s in segs
            ],
            key=lambda x: x["start"],
        )

        per_speaker: Dict[str, List[str]] = {sp: [] for sp in speaker_segs}
        segments_with_text: List[dict]    = []

        raw_segs = whisper_result.get("segments", [])
        if raw_segs:
            for seg in raw_segs:
                seg_start = seg["start"]
                seg_end   = seg["end"]
                seg_text  = seg["text"].strip()
                if not seg_text:
                    continue

                words = seg.get("words", [])
                if words:
                    current_speaker: str | None = None
                    current_words:   List[str]  = []
                    current_start:   float      = seg_start

                    for w in words:
                        w_start = w.get("start", seg_start)
                        w_end   = w.get("end",   seg_end)
                        w_mid   = (w_start + w_end) / 2
                        spk     = self._speaker_at(w_mid, timeline, speaker_segs)

                        if spk != current_speaker:
                            if current_speaker and current_words:
                                chunk = "".join(current_words).strip()
                                if chunk:
                                    per_speaker.setdefault(current_speaker, []).append(chunk)
                                    segments_with_text.append({
                                        "start":   round(current_start, 2),
                                        "end":     round(w_start, 2),
                                        "text":    chunk,
                                        "speaker": current_speaker,
                                    })
                            current_speaker = spk
                            current_words   = []
                            current_start   = w_start

                        current_words.append(w.get("word", ""))

                    if current_speaker and current_words:
                        chunk = "".join(current_words).strip()
                        if chunk:
                            per_speaker.setdefault(current_speaker, []).append(chunk)
                            segments_with_text.append({
                                "start":   round(current_start, 2),
                                "end":     round(seg_end, 2),
                                "text":    chunk,
                                "speaker": current_speaker,
                            })
                else:
                    spk = self._speaker_at((seg_start + seg_end) / 2, timeline, speaker_segs)
                    per_speaker.setdefault(spk, []).append(seg_text)
                    segments_with_text.append({
                        "start":   round(seg_start, 2),
                        "end":     round(seg_end, 2),
                        "text":    seg_text,
                        "speaker": spk,
                    })
        else:
            sp = list(speaker_segs.keys())[0] if speaker_segs else "SPEAKER_00"
            per_speaker[sp] = [full_text]
            segments_with_text.append({"start": 0.0, "end": 0.0, "text": full_text, "speaker": sp})

        per_speaker_joined = {sp: " ".join(txts).strip() for sp, txts in per_speaker.items() if txts}
        conversation       = self._build_conversation(segments_with_text)

        log.info(
            f"aligned {len(segments_with_text)} segments across "
            f"{len(per_speaker_joined)} speaker(s)"
        )
        return full_text, per_speaker_joined, segments_with_text, conversation

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _speaker_at(
        t: float,
        timeline: List[dict],
        speaker_segs: Dict[str, List[dict]],
    ) -> str:
        """Find the speaker at time t using the diarization timeline."""
        
        # ── If we have a timeline, find the speaker ──
        if timeline:
            # First, try exact match
            for ts in timeline:
                # Add a small tolerance for edge cases
                if ts["start"] - 0.1 <= t <= ts["end"] + 0.1:
                    return ts["speaker"]
            
            # If no exact match, find the closest segment
            closest = min(
                timeline,
                key=lambda ts: min(abs(ts["start"] - t), abs(ts["end"] - t))
            )
            return closest["speaker"]
        
        # ── Fallback: use the first speaker ──
        if speaker_segs:
            return list(speaker_segs.keys())[0]
        
        return "SPEAKER_00"

    @staticmethod
    def _build_conversation(segments_with_text: List[dict]) -> List[dict]:
        """Merge consecutive same-speaker segments into single dialogue turns."""
        conversation: List[dict] = []
        for entry in sorted(segments_with_text, key=lambda x: x["start"]):
            spk  = entry["speaker"]
            text = entry["text"].strip()
            if not text:
                continue
            if conversation and conversation[-1]["speaker"] == spk:
                conversation[-1]["text"] += " " + text
                conversation[-1]["end"]   = entry["end"]
            else:
                conversation.append({
                    "speaker": spk,
                    "start":   round(entry["start"], 2),
                    "end":     round(entry["end"],   2),
                    "text":    text,
                })
        return conversation


transcript_alignment_service = TranscriptAlignmentService()
