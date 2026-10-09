"""Auto GPU / CPU: use the GPU only when it is really usable AND likely faster, otherwise the CPU.
mode: "auto" (default) | "cpu" | "cuda"  (set from Settings, key "device" in config.json)"""
_MODE = ["auto"]


def set_mode(m):
    _MODE[0] = m if m in ("auto", "cpu", "cuda") else "auto"


def mode():
    return _MODE[0]


def whisper_plans():
    """List of (device, compute_type) to try in order for faster-whisper; the last one is always the CPU.
    Auto: GPU only if CTranslate2 supports fast half precision on it (old cards such as a 940MX do not -> CPU int8 is faster)."""
    cpu = [("cpu", "int8")]
    if _MODE[0] == "cpu":
        return cpu
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            types = set(ctranslate2.get_supported_compute_types("cuda"))
            for ct in ("int8_float16", "float16"):
                if ct in types:
                    return [("cuda", ct)] + cpu
            if _MODE[0] == "cuda" and types:                  # forced by the user
                return [("cuda", "int8" if "int8" in types else "float32")] + cpu
    except Exception:
        pass
    return cpu


def torch_gpu(min_gb=3.5):
    """True when PyTorch (Demucs) can use a CUDA card that is big and modern enough to beat the CPU."""
    if _MODE[0] == "cpu":
        return False
    try:
        import torch
        if not torch.cuda.is_available():
            return False
        if _MODE[0] == "cuda":
            return True
        p = torch.cuda.get_device_properties(0)
        return p.total_memory / 1024 ** 3 >= min_gb and p.major >= 6      # Pascal or newer with enough VRAM
    except Exception:
        return False


def label():
    p = whisper_plans()[0]
    return "GPU" if p[0] == "cuda" else "CPU"
