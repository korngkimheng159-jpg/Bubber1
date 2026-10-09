import re
from dataclasses import dataclass

@dataclass
class Seg:
    start: float
    end: float
    text: str
    gender: str = "female"
    src: str = ""
    voice: str = ""          # voice profile name, e.g. "Actress 1"
    speaker: str = ""        # speaker label from the transcriber (S1, S2 ...), "" = unknown

def fmt(t):
    ms = int(round(max(t, 0) * 1000))
    h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def parse_time(s):
    parts = s.strip().replace(",", ".").split(":")
    parts = ["0"] * (3 - len(parts)) + parts
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

_T = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")

def parse_srt(text):
    text = text.replace("\r\n", "\n").replace("\ufeff", "")
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.split("\n")
        for i, l in enumerate(lines):
            m = _T.search(l)
            if m:
                g = m.groups()
                s = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3].ljust(3, "0")[:3]) / 1000
                e = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7].ljust(3, "0")[:3]) / 1000
                out.append(Seg(s, e, "\n".join(lines[i + 1:]).strip()))
                break
    return out

def to_srt(segs):
    return "\n".join(f"{i}\n{fmt(s.start)} --> {fmt(s.end)}\n{s.text}\n" for i, s in enumerate(segs, 1))

def read_srt(path):
    return parse_srt(open(path, encoding="utf-8-sig", errors="ignore").read())

def write_srt(path, segs):
    open(path, "w", encoding="utf-8").write(to_srt(segs))
