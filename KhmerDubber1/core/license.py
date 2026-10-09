"""Licensing for rented copies: signed license keys (Ed25519), expiry date, optional lock to one computer.
The app only holds the PUBLIC key, so a customer cannot make a key; keys are issued with license_admin.py (owner only,
needs license_private.key). Works offline. A clock set back is detected (last-seen time is stored)."""
import base64, hashlib, hmac, json, os, platform, time, uuid
from datetime import date, datetime, timezone
from pathlib import Path

PUBLIC_KEY_HEX = "41f7890ddad94e544e4c0de91df58d71e142def9973698f90a3491db119b416b"
PREFIX = "KDL1-"
DIR = Path.home() / ".khmer_dubber"
KEY_FILE, STATE_FILE = DIR / "license.key", DIR / ".lic_state"


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def machine_id():
    """Stable id of this computer, shown as XXXX-XXXX-XXXX-XXXX (customer sends it to the owner to get a locked key)."""
    raw = ""
    try:
        if platform.system() == "Windows":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
                raw = winreg.QueryValueEx(k, "MachineGuid")[0]
        elif os.path.exists("/etc/machine-id"):
            raw = open("/etc/machine-id").read().strip()
    except Exception:
        raw = ""
    raw = raw or f"{uuid.getnode()}-{platform.node()}"
    h = hashlib.sha256(("kd|" + raw).encode()).hexdigest()[:16].upper()
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


def parse(key):
    """-> (payload dict, error). Verifies the signature only."""
    try:
        key = "".join(str(key).split())
        if not key.startswith(PREFIX):
            return None, "key មិនត្រឹមត្រូវ (ត្រូវចាប់ផ្តើមដោយ KDL1-)"
        body, sig = key[len(PREFIX):].split(".")
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX)).verify(_b64d(sig), _b64d(body))
        return json.loads(_b64d(body)), ""
    except ImportError:
        return None, "ខ្វះ package 'cryptography' (pip install cryptography)"
    except Exception:
        return None, "key មិនត្រឹមត្រូវ ឬត្រូវបានកែប្រែ"


def _state_mac(ts):
    return hmac.new(machine_id().encode(), str(ts).encode(), hashlib.sha256).hexdigest()[:20]


def _clock_ok():
    """False when the computer clock was moved BACK more than a day (used to stretch an expired licence)."""
    now = int(time.time())
    try:
        ts, mac = STATE_FILE.read_text().split(":")
        if hmac.compare_digest(mac, _state_mac(ts)) and now < int(ts) - 86400:
            return False
        last = max(int(ts), now) if hmac.compare_digest(mac, _state_mac(ts)) else now
    except Exception:
        last = now
    try:
        DIR.mkdir(exist_ok=True); STATE_FILE.write_text(f"{last}:{_state_mac(last)}")
    except Exception:
        pass
    return True


def check(key=None):
    """-> {valid, reason, name, plan, exp, days_left, id}. key=None reads the saved one."""
    if key is None:
        try:
            key = KEY_FILE.read_text(encoding="utf-8")
        except Exception:
            return {"valid": False, "reason": "មិនទាន់មាន License", "days_left": 0}
    p, err = parse(key)
    if not p:
        return {"valid": False, "reason": err, "days_left": 0}
    out = {"valid": False, "name": p.get("name", ""), "plan": p.get("plan", ""), "exp": p.get("exp", ""), "id": p.get("id", ""), "days_left": 0}
    hw = str(p.get("hwid", "")).strip().upper()
    if hw and hw != machine_id():
        out["reason"] = "License នេះចងជាប់នឹងកុំព្យូទ័រផ្សេង"; return out
    try:
        exp = date.fromisoformat(p["exp"]) if p.get("exp") else None
    except Exception:
        out["reason"] = "កាលបរិច្ឆេទ License មិនត្រឹមត្រូវ"; return out
    if not _clock_ok():
        out["reason"] = "ម៉ោងកុំព្យូទ័រត្រូវបានកែថយក្រោយ — សូមកែម៉ោងឲ្យត្រឹមត្រូវ"; return out
    if exp:
        out["days_left"] = (exp - datetime.now(timezone.utc).astimezone().date()).days
        if out["days_left"] < 0:
            out["reason"] = f"License ផុតកំណត់ហើយ ({p['exp']})"; return out
    else:
        out["days_left"] = 99999                        # no expiry = lifetime
    out["valid"], out["reason"] = True, ""
    out["gkey"] = str(p.get("gkey", "")).strip()          # optional Gemini key(s) provided by the owner with this licence
    return out


def save(key):
    DIR.mkdir(exist_ok=True)
    KEY_FILE.write_text("".join(str(key).split()), encoding="utf-8")
