# -*- coding: utf-8 -*-
"""抽取结果落盘缓存（2026-10-12 用户要求）：按 (文本 sha1, 抽取器版本, loose 开关) 缓存 extract() 的结果，
保留集与后处理调参时重跑覆盖统计不再重复抽取。

* 抽取器版本＝被调用代码根下 lingshu_ng/chain/{extract,loose}.py 源码的 sha1 前 12 位——改一个字就换版本，旧缓存自动失效；
  不同代码根（v7/v8 快照、本 worktree）各用各的版本，不会串。
* 落盘：/workspace/work/ls/_shared/extract_cache/<版本>.json（一个版本一个文件，进程结束前 flush；先写临时文件再 os.replace）。
* 只缓存「单句/单段 → 事件列表」这一步（零 LLM 的规则抽取，省的是时间不是钱）；引擎写入期抽取（被测系统本身）不走缓存。"""
import atexit, hashlib, json, os, threading

ROOT_DIR = os.environ.get("LINGSHU_EXTRACT_CACHE") or "/workspace/work/ls/_shared/extract_cache"
_mem, _dirty, _lock = {}, set(), threading.Lock()
STATS = {"hit": 0, "miss": 0}


def version(extract_module) -> str:
    d = os.path.dirname(extract_module.__file__)
    h = hashlib.sha1()
    for f in ("extract.py", "loose.py"):
        p = os.path.join(d, f)
        if os.path.exists(p):
            h.update(open(p, "rb").read())
    return h.hexdigest()[:12]


def _load(ver):
    if ver not in _mem:
        p = os.path.join(ROOT_DIR, ver + ".json")
        try:
            _mem[ver] = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            _mem[ver] = {}
    return _mem[ver]


def flush():
    for ver in list(_dirty):
        p = os.path.join(ROOT_DIR, ver + ".json")
        os.makedirs(ROOT_DIR, exist_ok=True)
        tmp = f"{p}.{os.getpid()}.tmp"
        try:
            old = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
        except (OSError, ValueError):
            old = {}
        old.update(_mem[ver])
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(old, f, ensure_ascii=False)
        os.replace(tmp, p)
        _dirty.discard(ver)


atexit.register(flush)

_FIELDS = ("op", "entity", "attr", "value", "alt", "reason", "line", "quote", "first", "rename_from_seq", "extra")


def wrap(extract_module):
    """返回带缓存的 extract(text, loose=None)；结果还原为 Event 对象。"""
    ver = version(extract_module)
    Event = extract_module.Event
    raw = extract_module.extract

    def extract(text, loose=None):
        lz = extract_module.LOOSE if loose is None else loose
        k = hashlib.sha1(((text or "") + ("\x01L" if lz else "\x01S")).encode("utf-8")).hexdigest()
        with _lock:
            c = _load(ver)
            hit = c.get(k)
        if hit is not None:
            STATS["hit"] += 1
            return [Event(**dict(zip(_FIELDS, x))) for x in hit]
        STATS["miss"] += 1
        evs = raw(text, loose=loose)
        with _lock:
            c[k] = [[getattr(e, f) for f in _FIELDS] for e in evs]
            _dirty.add(ver)
        return evs
    extract.version = ver
    return extract
