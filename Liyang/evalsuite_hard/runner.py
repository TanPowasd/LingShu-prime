#!/usr/bin/env python3
"""子进程入口：python runner.py --impl legacy|ng --dim <name> --seed S [--arg k=v ...] → 打印 @@RESULT <json>。"""
import argparse, importlib, json, os, sys, time, traceback, warnings

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
warnings.filterwarnings("ignore")


def emit(d):
    sys.stdout.write("\n@@RESULT " + json.dumps(d, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True)
    ap.add_argument("--dim", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--arg", action="append", default=[])
    a = ap.parse_args()
    kw = {}
    for s in a.arg:
        k, v = s.split("=", 1)
        kw[k] = json.loads(v)
    from hadapt import NA, Adapter
    t0 = time.perf_counter()
    mod = importlib.import_module(f"dims.d_{a.dim}")
    try:
        if getattr(mod, "RAW", False):
            r = mod.run(a.impl, a.seed, **kw)
        else:
            r = mod.run(Adapter(a.impl), a.seed, **kw)
        emit({"status": "OK", "impl": a.impl, "raw": r, "sec": round(time.perf_counter() - t0, 2)})
    except NA as ex:
        emit({"status": "NA", "reading": str(ex)[:300], "sec": round(time.perf_counter() - t0, 2)})
    except Exception as ex:
        tb = traceback.format_exc().strip().splitlines()
        emit({"status": "ERR", "reading": f"{type(ex).__name__}: {str(ex)[:200]} @ {' | '.join(x.strip() for x in tb[-4:])[:300]}",
              "sec": round(time.perf_counter() - t0, 2)})


if __name__ == "__main__":
    main()
