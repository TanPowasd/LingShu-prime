# -*- coding: utf-8 -*-
"""网络外联观测（粗粒度采样）：每 3 秒读 /proc/<pid>/fd 的 socket inode 对 /proc/net/tcp{,6}（本机无 ss），抓 everos server 进程（命令行含 'everos server start'）的非回环连接。
只记远端 ip:port 与进程，不记内容。输出 JSONL：runs/everos/egress_samples.jsonl。另记 DNS 解析不到的域名不在此列（如实：采样会漏掉 <3s 的短连接）。"""
import json, os, re, subprocess, sys, time
out = sys.argv[1] if len(sys.argv) > 1 else "runs/everos/egress_samples.jsonl"
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 4 * 3600
seen = {}
t0 = time.time()
while time.time() - t0 < dur:
    pids = set()
    for p in os.listdir("/proc"):
        if p.isdigit():
            try:
                cmd = open(f"/proc/{p}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace")
            except OSError:
                continue
            if "everos server start" in cmd and "bash" not in cmd.split()[0]:
                pids.add(p)
    inode2pid = {}
    for p in pids:
        try:
            for fd in os.listdir(f"/proc/{p}/fd"):
                try:
                    l = os.readlink(f"/proc/{p}/fd/{fd}")
                except OSError:
                    continue
                if l.startswith("socket:["):
                    inode2pid[l[8:-1]] = p
        except OSError:
            pass
    for tbl in ("/proc/net/tcp", "/proc/net/tcp6", "/proc/net/udp", "/proc/net/udp6"):
        try:
            rows = open(tbl).read().splitlines()[1:]
        except OSError:
            continue
        for r in rows:
            c = r.split()
            if len(c) < 10 or c[9] not in inode2pid:
                continue
            rem = c[2]
            hexip, hexport = rem.split(":")
            port = int(hexport, 16)
            if len(hexip) == 8:
                ip = ".".join(str(int(hexip[i:i + 2], 16)) for i in (6, 4, 2, 0))
            else:
                ip = "v6:" + hexip
            if port == 0 or ip.startswith("127.") or ip == "0.0.0.0" or hexip in ("00000000000000000000000001000000", "0000000000000000FFFF00000100007F") or hexip.endswith("0100007F"):
                continue
            key = (inode2pid[c[9]], ip, port)
            if key not in seen:
                seen[key] = 1
                with open(out, "a") as f:
                    f.write(json.dumps({"wall": time.strftime("%H:%M:%S", time.gmtime(time.time() + 8 * 3600)), "pid": key[0],
                                        "table": tbl, "peer": f"{ip}:{port}", "state": c[3]}) + "\n")
    with open(out + ".heartbeat", "w") as f:
        f.write(json.dumps({"last": time.time(), "pids": sorted(pids), "uniq": len(seen)}))
    time.sleep(3)
