# -*- coding: utf-8 -*-
"""破坏性验证：进程内导入的探针，失败时必须照样报红，不许静默返空/放行

⛔ 2026-08-17 改判据：以前这里断言「HTTP 不是 200」。那是拿**接口成败**去代表
   **项目健康**，两个问题混成一个。真实后果：一个项目探针真红了（该让人看见），
   驾驶舱的重算按钮打出「✗ 重算失败」——状态其实已经算好写下去了，人只会以为
   按钮坏了，从此不点。现在判据回到直接证据：**红有没有报出来、值有没有被悄悄填上**。
   （坑库 T17）
"""
import io, json, os, shutil, socket, subprocess, tempfile, time, urllib.request, urllib.error
BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # tests 的上一级就是 brain-console
# release_pkg 是作者本机的发布目录，别人 clone 下来只有自己打出来的 dist——两个都认，
# 谁在就用谁，否则这行在别人机器上直接 FileNotFoundError。首选保持原样，不改语义。
_CAND = [os.path.join(BC, d, "lingtaios.exe") for d in ("dist", "release_pkg")]
EXE = next((p for p in _CAND if os.path.isfile(p)), _CAND[0])
DN = subprocess.DEVNULL

def sh(c):
    r = subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (r.stdout or b"").decode("mbcs", errors="replace")

CASES = [
    ("A healthy",          "ITEMS = [1,2,3,4,5,6,7]\n",      "ITEMS",   True,  7),
    ("B attr missing",     "ITEMS = [1,2,3]\n",              "NOPE",    False, None),
    ("C module raises",    "raise RuntimeError('boom')\n",   "ITEMS",   False, None),
    ("D syntax error",     "def (:\n",                       "ITEMS",   False, None),
    ("E attr not sized",   "ITEMS = 42\n",                   "ITEMS",   False, None),
    ("F module missing",   None,                             "ITEMS",   False, None),
]

sh('taskkill /F /IM lingtaios.exe /T'); time.sleep(1)
subprocess.Popen([EXE, "--no-browser"], cwd=os.path.dirname(EXE), stdout=DN, stderr=DN)
for _ in range(90):
    s = socket.socket(); s.settimeout(0.4)
    up = s.connect_ex(("127.0.0.1", 8765)) == 0; s.close()
    if up: break
    time.sleep(0.5)
print("exe up:", up, "\n")

def run(proj):
    req = urllib.request.Request("http://127.0.0.1:8765/api/run_generator",
                                 data=json.dumps({"path": proj}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))

passed = 0
for label, src, attr, want_ok, want_val in CASES:
    proj = tempfile.mkdtemp(prefix="destr_")
    brain = os.path.join(proj, "brain"); os.makedirs(brain)
    if src is not None:
        io.open(os.path.join(brain, "mymod.py"), "w", encoding="utf-8").write(src)
    json.dump({"project": "D", "root": ".", "probes": [
        {"name": "p", "type": "py_attr_len", "module": "mymod.py", "attr": attr}]},
        io.open(os.path.join(brain, "状态源.json"), "w", encoding="utf-8"), ensure_ascii=False)
    st, d = run(proj)
    sj = os.path.join(brain, "02_状态.json")
    doc = json.load(io.open(sj, encoding="utf-8")) if os.path.isfile(sj) else {}
    vals, alarms = doc.get("values", {}), doc.get("alarms", [])
    got_val = vals.get("p")
    if want_ok:
        ok = st == 200 and got_val == want_val and not alarms and d.get("alarms") == 0
        why = "value=%s alarms=%d api_alarms=%s" % (got_val, len(alarms), d.get("alarms"))
    else:
        # 必须报红：不许静默通过，也不许把值悄悄填成 0/None 当合格。
        # 三处都要对：状态文件里有告警、值是空的、**接口自己也把告警数报上来**
        # （只查文件的话，接口悄悄把红吞掉、界面显示一切正常，这里照样全绿）
        ok = (len(alarms) >= 1 and got_val is None
              and d.get("wrote") is True and (d.get("alarms") or 0) >= 1)
        why = "http=%s alarms=%d api=%s/%s value=%r | %s" % (
            st, len(alarms), d.get("wrote"), d.get("alarms"), got_val,
            (alarms[0][:60].replace("\n", " ") if alarms else "NO ALARM!"))
    passed += ok
    print("[%s] %-18s %s" % ("PASS" if ok else "FAIL", label, why))
    shutil.rmtree(proj, ignore_errors=True)

print("\n%d/%d destructive cases passed" % (passed, len(CASES)))
sh('taskkill /F /IM lingtaios.exe /T')
# 退出码要给：靠 runner 认末行文案，改一个字就静默变绿
import sys as _sys
_sys.exit(0 if passed == len(CASES) else 1)
