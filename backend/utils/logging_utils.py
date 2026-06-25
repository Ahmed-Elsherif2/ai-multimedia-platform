"""Structured stage logger with elapsed-time tracking."""
from __future__ import annotations

import functools
import time
from typing import Callable


class StageLogger:
    def __init__(self, service: str):
        self.service = service

    def info(self, msg: str) -> None:
        print(f"[{self.service}] {msg}")

    def error(self, msg: str) -> None:
        print(f"[{self.service}] ERROR: {msg}")

    def warn(self, msg: str) -> None:
        print(f"[{self.service}] WARN: {msg}")

    def timed(self, stage: str) -> Callable:
        """Decorator — logs start/end of *stage* with elapsed seconds."""
        def decorator(fn: Callable) -> Callable:
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                t0 = time.perf_counter()
                self.info(f"{stage} starting…")
                try:
                    result  = fn(*args, **kwargs)
                    elapsed = time.perf_counter() - t0
                    self.info(f"{stage} done ({elapsed:.1f}s)")
                    return result
                except Exception as exc:
                    elapsed = time.perf_counter() - t0
                    self.error(f"{stage} failed after {elapsed:.1f}s — {exc}")
                    raise
            return wrapper
        return decorator


def get_logger(service: str) -> StageLogger:
    return StageLogger(service)
