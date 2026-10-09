"""M2 验收：把 imgskill 从大脑库内核拿掉（内核只留 kernel_shim/imgskill.py 兼容薄壳），
内核不受影响；拆出的包自带上游守卫且全绿。

用法：python verify/brain_split_m2.py <dsh-memory 仓根>
（须在装了 brain-imgskill 的解释器里跑；Pillow / magick 至少其一）
"""
import ast, json, os, re, shutil, subprocess, sys, tempfile

SRC = os.path.abspath(sys.argv[1])
PY = sys.executable
SAMPLE = ["test_action_derive", "test_tasks", "test_auditview", "test_hot_cold", "test_issue84_portability"]


SHIM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "packages", "brain-imgskill",
                    "kernel_shim", "imgskill.py")


def run(args, cwd, pypath=None):
    env = dict(os.environ, PYTHONWARNINGS="ignore")
    if pypath:
        env["PYTHONPATH"] = pypath
    r = subprocess.run([PY, "-X", "utf8"] + args, cwd=cwd, capture_output=True, text=True, timeout=600, env=env)
    txt = r.stdout + r.stderr
    p = len(re.findall(r"\[PASS\]|\bPASS\b", txt)); f = len(re.findall(r"\[FAIL\]|\bFAIL\b", txt))
    m = re.search(r"(\d+) passed, (\d+) failed", txt)
    if m:
        p, f = int(m.group(1)), int(m.group(2))
    fails = re.findall(r"\[FAIL\]\s*([^\n·]{0,60})", txt)
    return {"rc": r.returncode, "pass": p, "fail": f, "fail_names": [x.strip() for x in fails][:6]}


out = {}
# 1 静态：内核里谁 import imgskill
users = []
for d, _, fs in os.walk(os.path.join(SRC, "md_cg")):
    for fn in fs:
        if fn.endswith(".py"):
            path = os.path.join(d, fn)
            try:
                tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
            except SyntaxError:
                continue
            for n in ast.walk(tree):
                names = [a.name for a in n.names] if isinstance(n, (ast.Import, ast.ImportFrom)) else []
                mod = getattr(n, "module", None) or ""
                if "imgskill" in mod or any("imgskill" in x for x in names):
                    users.append(os.path.relpath(path, SRC))
out["kernel_modules_importing_imgskill"] = sorted(set(users))
mentions = subprocess.run(["grep", "-rl", "imgskill", "--include=*.py", "md_cg"], cwd=SRC,
                          capture_output=True, text=True).stdout.split()
out["kernel_files_mentioning_imgskill"] = sorted(mentions)

# 2 内核：原样 vs 拆后（imgskill.py → 兼容薄壳；test_imgskill.py 随包迁走）
work = tempfile.mkdtemp(prefix="m2_")
before, after = os.path.join(work, "before"), os.path.join(work, "after")
ign = shutil.ignore_patterns(".git", "node_modules", "__pycache__")
shutil.copytree(SRC, before, ignore=ign); shutil.copytree(SRC, after, ignore=ign)
shutil.copyfile(SHIM, os.path.join(after, "md_cg", "imgskill.py"))
os.remove(os.path.join(after, "md_cg", "test_imgskill.py"))

# 3 拆出的包自带的上游守卫（逐字节原件）：裸跑 vs 内核留薄壳
out["package_guard_without_shim"] = run(["-m", "brain_imgskill.test_imgskill"], cwd=tempfile.gettempdir())
out["package_guard_with_shim"] = run(["-m", "brain_imgskill.test_imgskill"], cwd=tempfile.gettempdir(), pypath=after)
out["upstream_guard_in_place"] = run(["-m", "md_cg.test_imgskill"], cwd=before)
probe = ("import tempfile;from md_cg import mcp_server as M;from md_cg.mdcos import MdCGSecure;"
         "from md_cg.security import Principal;"
         "cg=MdCGSecure(tempfile.mkdtemp(),principal=Principal(actor='m2',role='designer',can_admin=True,session='m2'));"
         "o=M._cg_call(cg,{'op':'help'});print('[PASS] cg help' if o else '[FAIL] cg help')")
out["kernel"] = {}
for t in SAMPLE + ["<cg help probe>"]:
    args = ["-c", probe] if t.startswith("<") else ["-m", f"md_cg.{t}"]
    out["kernel"][t] = {"before": run(args, before), "after": run(args, after)}
# 4 薄壳保住的公开面
out["shim_surface"] = run(["-c", "from md_cg import imgskill as S; import brain_imgskill.imgskill as B; "
                           "print('[PASS] same module' if S is B else '[FAIL] same module')"], cwd=after)
out["shim_cli_help"] = {"rc": subprocess.run([PY, "-X", "utf8", "-m", "md_cg.imgskill", "--help"], cwd=after,
                                             capture_output=True, text=True).returncode}
shutil.rmtree(work, ignore_errors=True)
print(json.dumps(out, ensure_ascii=False, indent=1))
