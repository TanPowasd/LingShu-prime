"""M3（task 半）验收：内核打 kernel_patch/M3_task.patch 后，task 由插件 brain-agenda 经 LSPI 登记处服务。

用法：python verify/brain_split_m3.py <dsh-memory 仓根>   （解释器里须装 lspi-core / lspi-brain-host / brain-agenda）
读数：
  1 上游 test_tasks 与 6 个用到 tasks 的内核测试：拆前（原样）→ 拆后（补丁 + 插件）
  2 拆后但插件未装：哪些测试变红、上下文装配是否降级（迁移账本依据）
"""
import json, os, re, shutil, subprocess, sys, tempfile

SRC = os.path.abspath(sys.argv[1])
PY = sys.executable
HERE = os.path.dirname(os.path.abspath(__file__))
PATCH = os.path.join(HERE, "..", "packages", "brain-agenda", "kernel_patch", "M3_task.patch")
TESTS = ["test_tasks", "test_blindspot_tickets", "test_lifecycle_retire_leak", "test_recall_face_guards",
         "test_read_face_input_gates", "test_security_audit_v21", "test_ccg_form_parity", "test_action_derive"]
HIDE = "import sys,runpy; sys.modules['brain_agenda']=None; runpy.run_module('md_cg.%s', run_name='__main__')"


def run(args, cwd):
    r = subprocess.run([PY, "-X", "utf8"] + args, cwd=cwd, capture_output=True, text=True, timeout=900,
                       env=dict(os.environ, PYTHONWARNINGS="ignore"))
    lines = [x for x in (r.stdout + r.stderr).splitlines() if x.strip()]
    summ = next((x.strip() for x in reversed(lines)
                 if re.search(r"通过|PASS=|ALL GREEN|失败|passed|FAIL", x)), lines[-1] if lines else "")
    return {"rc": r.returncode, "summary": summ[:120]}


work = tempfile.mkdtemp(prefix="m3_")
before, after = os.path.join(work, "before"), os.path.join(work, "after")
ign = shutil.ignore_patterns(".git", "node_modules", "__pycache__")
shutil.copytree(SRC, before, ignore=ign); shutil.copytree(SRC, after, ignore=ign)
p = subprocess.run(["git", "apply", "-p1", "--whitespace=nowarn", os.path.abspath(PATCH)], cwd=after, capture_output=True, text=True)
out = {"patch_applied": p.returncode == 0, "patch_out": p.stdout.strip().splitlines()}
out["tests"] = {t: {"before": run(["-m", f"md_cg.{t}"], before),
                    "after_with_plugin": run(["-m", f"md_cg.{t}"], after),
                    "after_without_plugin": run(["-c", HIDE % t], after)} for t in TESTS}
probe = ("import sys,tempfile;%s from md_cg import mcp_server as M;from md_cg.mdcos import MdCGSecure;"
         "from md_cg.security import Principal;"
         "cg=MdCGSecure(tempfile.mkdtemp(),principal=Principal(actor='m3',role='designer',can_admin=True,session='m3'));"
         "o=M._cg_call(cg,{'op':'task','name':'探针任务','plan':'p'});"
         "pk=cg.session_recall();"
         "import json;print(json.dumps({'task_ok':o.get('ok'),'task_status':o.get('status'),"
         "'pack_degraded':(pk or {}).get('degraded')},ensure_ascii=False))")
for k, hide in (("probe_with_plugin", ""), ("probe_without_plugin", "sys.modules['brain_agenda']=None;")):
    r = subprocess.run([PY, "-X", "utf8", "-c", probe % hide], cwd=after, capture_output=True, text=True,
                       env=dict(os.environ, PYTHONWARNINGS="ignore"))
    out[k] = (r.stdout.strip().splitlines() or [""])[-1] or r.stderr.strip().splitlines()[-1][:200]
shutil.rmtree(work, ignore_errors=True)
print(json.dumps(out, ensure_ascii=False, indent=1))
