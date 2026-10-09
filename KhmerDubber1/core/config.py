import json
from pathlib import Path

DIR = Path.home() / ".khmer_dubber"
DIR.mkdir(exist_ok=True)
FILE = DIR / "config.json"
DEFAULTS = {
    "gemini_key": "", "tr_engine": "","gemini_model": "gemini-flash-latest",
    "stt_engine": "Gemini", "whisper_size": "base", "sub_font": "Khmer UI",
    "target_lang": "Khmer", "source_lang": "Auto", "device": "auto",
    "sub_style": None, "music_mode": "fast", "theme": "Neon Cyan", "mute_orig": False, "export_dir": "", "export_quality": "fast", "export_res": 0, "export_encoder": "auto", "lite_translate": False, "short_translate": True, "auto_short": True, "sub_chars": 28, "stage": None, "sub_pos": [0.5, 0.88],      # Khmer subtitle look + position (set from the app)
}

PROVISIONED = [""]      # Gemini key(s) that came with the licence (customer never types them; never written to config.json)


def apply_license(cfg):
    """No key of the customer's own -> use the key that the owner put in the licence (if any)."""
    try:
        from . import license
        st = license.check()
        PROVISIONED[0] = st.get("gkey", "") if st.get("valid") else ""
    except Exception:
        PROVISIONED[0] = ""
    if PROVISIONED[0] and not str(cfg.get("gemini_key", "")).strip():
        cfg["gemini_key"] = PROVISIONED[0]
    return cfg


def load():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    if str(cfg.get("gemini_model", "")).startswith("gemini-2."):   # retired / restricted models
        cfg["gemini_model"] = "gemini-flash-latest"
    cfg.pop("groq_key", None)                                   # Groq was removed
    try:                                                        # light .exe build has no Whisper -> default to Gemini
        import importlib.util
        if cfg.get("stt_engine") == "Whisper" and importlib.util.find_spec("faster_whisper") is None:
            cfg["stt_engine"] = "Gemini"
    except Exception:
        pass
    if str(cfg.get("stt_engine", "")).startswith("Groq"):
        cfg["stt_engine"] = "Whisper"
    try:
        from . import device
        device.set_mode(cfg.get("device", "auto"))
    except Exception:
        pass
    return apply_license(cfg)

def save(cfg):
    out = dict(cfg)
    if PROVISIONED[0] and out.get("gemini_key") == PROVISIONED[0]:
        out["gemini_key"] = ""                      # a licence-provided key is never stored in the customer's config file
    FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
