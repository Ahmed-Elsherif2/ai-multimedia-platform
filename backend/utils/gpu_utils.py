"""
GPU / device detection — shared by all ML services.

Usage
-----
from utils.gpu_utils import get_device, use_fp16

device = get_device()   # "cuda" | "cpu" | "mps"
fp16   = use_fp16()     # True only on CUDA — fp16 on CPU crashes Whisper
"""
from __future__ import annotations

_cached: str | None = None


def get_device(override: str = "auto") -> str:
    """
    Resolve the best available torch device.

    Parameters
    ----------
    override : value of TORCH_DEVICE env var ("auto" | "cuda" | "cpu" | "mps")

    Returns
    -------
    "cuda", "mps", or "cpu"
    """
    global _cached
    if override not in ("auto", ""):
        return override
    if _cached is not None:
        return _cached
    try:
        import torch
        if torch.cuda.is_available():
            _cached = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            _cached = "mps"
        else:
            _cached = "cpu"
    except ImportError:
        _cached = "cpu"
    return _cached


def use_fp16(override: str = "auto") -> bool:
    """Return True only when running on CUDA — fp16 crashes on CPU/MPS."""
    return get_device(override) == "cuda"


def torch_device(override: str = "auto"):
    """Return a torch.device instance for the resolved device."""
    import torch
    return torch.device(get_device(override))
