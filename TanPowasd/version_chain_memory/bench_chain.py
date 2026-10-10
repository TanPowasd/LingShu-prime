"""Zero-model structured control for hive-memory-bench chain/.

This benchmark feeds the new core the generator's confirmed event records.
It measures the version-chain index and query router independently from text
extraction.  It is intentionally labelled a structured control, not a
natural-language score or a replacement for the official retrieval arms.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import socket
import subprocess
import sys
from unittest.mock import patch

from version_chain_memory import Event, Query, VersionChainMemory


def load_memory(root: Path) -> tuple[VersionChainMemory, list[dict], dict[str, int]]:
    chain = root / "chain"
    keys = json.loads((chain / "keys/keys.json").read_text(encoding="utf-8"))
    log = json.loads((chain / "keys/synth_log.json").read_text(encoding="utf-8"))
    corpus = json.loads((chain / "corpus/corpus.json").read_text(encoding="utf-8"))
    by_source = {(row["doc"], row["seq"]): row for row in corpus}
    memory = VersionChainMemory()
    operations = {"create": "set", "change": "set", "restore": "restore",
                  "retire": "retire", "unresolve": "unresolved", "resolve": "resolve"}
    count = 0
    for chain_no, item in enumerate(log["chains"]):
        if item.get("is_decoy"):
            continue
        for event_no, event in enumerate(item["events"]):
            op = operations[event["kev"]]
            source = by_source.get((item["doc"], event["seq"]), {})
            quote = source.get("text", "")
            kwargs = dict(event_id=f"{item['doc_id']}:{chain_no}:{event_no}:{event['seq']}",
                          source_id=source.get("cid", f"{item['doc_id']}#{event['seq']}"),
                          entity=item["subject"], facet=item["slot"], operation=op,
                          effective_at=event["seq"], recorded_at=event["seq"],
                          value=event["to"], previous=event["frm"],
                          alternative=event.get("alt"), reason=event.get("reason"),
                          quote=quote, metadata={"kev": event["kev"]})
            memory.add_event(Event(**kwargs))
            count += 1
    return memory, keys, {"chains": sum(not x.get("is_decoy") for x in log["chains"]), "events": count}


def mode_for(question: dict) -> Query:
    typ = question["type"]
    at = float(question.get("sample_at_seq") or math.inf)
    if typ == "变更":
        return Query(question["subject"], question["slot"], mode="chain", at=math.inf)
    if typ == "缘由":
        return Query(question["subject"], question["slot"], mode="reason",
                     at=at, event_at=at)
    if typ == "状态归属":
        return Query(question["subject"], question["slot"], mode="state", at=at)
    return Query(question["subject"], question["slot"], mode="at", at=at)


def equal_chain(pred: list[dict], expected: list[dict]) -> bool:
    fields = ("seq", "from", "to")
    return len(pred) == len(expected) and all(
        all(row.get(field) == exp.get(field) for field in fields)
        for row, exp in zip(pred, expected)
    )


def score(memory: VersionChainMemory, keys: list[dict]) -> dict:
    by_type = {}
    exact = 0
    for question in keys:
        result = memory.query(mode_for(question))
        answer = question["answer"]
        typ = question["type"]
        if typ == "变更":
            ok = equal_chain(result["chain"], answer.get("chain", []))
        else:
            ok = (result["value"] == answer.get("value") and
                  result["state"] == answer.get("state") and
                  result["at"] == answer.get("at_seq"))
        by_type.setdefault(typ, [0, 0])
        by_type[typ][1] += 1
        by_type[typ][0] += int(ok)
        exact += int(ok)
    return {"exact": exact, "questions": len(keys),
            "exact_rate": exact / len(keys) if keys else 1.0,
            "by_type": {k: {"correct": v[0], "questions": v[1],
                             "rate": v[0] / v[1] if v[1] else 1.0}
                         for k, v in sorted(by_type.items())}}


def interval_control(memory: VersionChainMemory) -> dict:
    memory.set("control-1", "control", "control", "field", "A", effective_at=1, recorded_at=1)
    memory.set("control-2", "control", "control", "field", "B", effective_at=4, recorded_at=2)
    memory.set("control-3", "control", "control", "field", "C", effective_at=8, recorded_at=3)
    expected = {1: "A", 3: "A", 4: "B", 7: "B", 8: "C", 20: "C"}
    got = {at: memory.query(Query("control", "field", at=at))["value"] for at in expected}
    return {"passed": got == expected, "expected": expected, "got": got}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bench", type=Path, help="local hive-memory-bench checkout")
    parser.add_argument("--out", type=Path, default=Path("results/version-chain"))
    args = parser.parse_args()
    attempts: list[bool] = []

    def deny(*_args, **_kwargs):
        attempts.append(True)
        raise RuntimeError("network disabled")

    with patch.object(socket.socket, "connect", deny), \
         patch.object(socket.socket, "connect_ex", deny), \
         patch.object(socket, "create_connection", deny):
        memory, keys, counts = load_memory(args.bench.resolve())
        readings = score(memory, keys)
        interval = interval_control(VersionChainMemory())
    assert not attempts
    assert readings["exact"] == readings["questions"]
    assert interval["passed"]
    output = {"dataset": "hive-memory-bench/chain v0.2",
              "dataset_commit": "426a86a",
              "model_calls": 0, "network_attempts": 0,
              "scope": "structured event/state-chain control; extraction is not measured",
              "counts": counts, "readings": readings, "interval_control": interval,
              "statistics": memory.statistics()}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "readings.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if __import__("os").environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit(subprocess.call([sys.executable, "-B", "-X", "utf8", __file__, *sys.argv[1:]],
                                         env={**__import__("os").environ, "PYTHONHASHSEED": "0"}))
    main()
