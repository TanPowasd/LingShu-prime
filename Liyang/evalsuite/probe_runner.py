#!/usr/bin/env python3
"""子进程入口：在一个快照上跑单个探针 / 性质，打印一行 @@RESULT <json>。

用法（由 run_all 调用）：
  PYTHONPATH=<snapshot_root>:<evalsuite_dir> python probe_runner.py --impl legacy --probe i35-search-truncation
  ... --prop P01-layer-immutability --seeds 200
"""
import argparse, json, os, sys, time, traceback, warnings

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
warnings.filterwarnings("ignore")


def emit(d):
    sys.stdout.write("\n@@RESULT " + json.dumps(d, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True)
    ap.add_argument("--probe")
    ap.add_argument("--prop")
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--perf", type=int)
    ap.add_argument("--trace", action="store_true")
    a = ap.parse_args()
    from adapters import Adapter, NA
    if a.list:
        from probes import REG
        from props import PROPS
        emit({"probes": {k: {"issue": v["issue"], "title": v["title"]} for k, v in REG.items()},
              "props": {k: v["title"] for k, v in PROPS.items()}})
        return
    t0 = time.perf_counter()
    try:
        if a.check:
            A = Adapter(a.impl)
            emit({"verdict": "OK", "reading": getattr(A.mod, "__file__", "?")})
        elif a.perf:
            from perf import run_perf
            r = run_perf(a.impl, a.perf, trace=a.trace)
            r["verdict"] = "OK"
            r["sec"] = round(time.perf_counter() - t0, 3)
            emit(r)
        elif a.probe:
            from probes import REG
            spec = REG[a.probe]
            if spec["raw"]:
                v, reading = spec["fn"](a.impl)
            else:
                v, reading = spec["fn"](Adapter(a.impl))
            emit({"verdict": v, "reading": str(reading)[:300], "sec": round(time.perf_counter() - t0, 3)})
        else:
            from props import run_prop
            r = run_prop(a.prop, a.impl, a.seeds)
            r["sec"] = round(time.perf_counter() - t0, 3)
            emit(r)
    except NA as ex:
        emit({"verdict": "NA", "reading": str(ex)[:300], "sec": round(time.perf_counter() - t0, 3)})
    except Exception as ex:
        tb = traceback.format_exc().strip().splitlines()
        emit({"verdict": "ERR", "reading": f"{type(ex).__name__}: {str(ex)[:160]} @ {tb[-3].strip()[:120] if len(tb) > 2 else ''}",
              "sec": round(time.perf_counter() - t0, 3)})


if __name__ == "__main__":
    main()
