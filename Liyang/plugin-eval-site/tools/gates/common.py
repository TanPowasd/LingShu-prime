"""门槛 2–6 验证公用件（pes-e2e-gates）。只写 validation/_gates/、tools/gates/、tests/test_gates_*.py。"""
from __future__ import annotations
import hashlib, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # /workspace/work/pes
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
VAL = ROOT / "validation" / "_gates"
HMB = Path(os.environ.get("PES_HMB", "/workspace/work/ls/hmb"))
VALIDATION_ID = "_gates"


def sha256_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def wjson(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, p)


def rjson(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def append_jsonl(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")


def read_jsonl(p):
    out = []
    if not Path(p).exists():
        return out
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def git_head(d=ROOT) -> str:
    try:
        return subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception:
        return "?"


def now_cst() -> str:
    g = time.gmtime(time.time() + 8 * 3600)
    return f"{g.tm_year:04d}-{g.tm_mon:02d}-{g.tm_mday:02d}T{g.tm_hour:02d}:{g.tm_min:02d}:{g.tm_sec:02d}+08:00"
