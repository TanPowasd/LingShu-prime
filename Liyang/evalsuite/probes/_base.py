"""探针注册表与判定助手。

每个探针：@probe(pid, issue, title) 修饰的函数 fn(A) -> (verdict, reading)
  verdict ∈ {"BUG", "OK"}；能力缺失时抛 adapters.NA（由 runner 记为 NA）。
  raw=True 的探针拿到的是 impl 字符串（需在构造适配器前改动进程环境，如屏蔽 numpy）。
判定口径：每个探针的 OK 条件写在探针正文里，对所有实现一致，不读实现内部状态。
"""
import threading
import time

REG = {}


def probe(pid, issue, title, raw=False):
    def deco(fn):
        assert pid not in REG, pid
        REG[pid] = {"fn": fn, "issue": issue, "title": title, "raw": raw, "module": fn.__module__}
        return fn
    return deco


def judge(bad, reading):
    return ("BUG" if bad else "OK", reading)


def deadline(fn, sec):
    """在守护线程里跑 fn，最多等 sec 秒。返回 (finished, result, elapsed)；fn 抛出的异常原样在调用方重抛。"""
    box = {}

    def run():
        try:
            box["r"] = fn()
        except BaseException as ex:  # noqa
            box["e"] = ex
    t0 = time.perf_counter()
    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(sec)
    dt = time.perf_counter() - t0
    if th.is_alive():
        return False, None, dt
    if "e" in box:
        raise box["e"]   # NA → runner 记 NA；其他异常 → ERR（不让「抛异常但很快」被当成性能达标）
    return True, box.get("r"), dt


def raises(fn, *exc):
    try:
        fn()
        return None
    except exc as ex:
        return ex
