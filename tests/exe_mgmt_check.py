# -*- coding: utf-8 -*-
"""项目管理在打包后的 exe 里也要能用——源码态过了不代表 exe 过了"""
import io, json, os, shutil, socket, subprocess, tempfile, time, urllib.error, urllib.request
BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # tests 的上一级就是 brain-console
# release_pkg 是作者本机的发布目录，别人 clone 下来只有自己打出来的 dist——两个都认，
# 谁在就用谁，否则这行在别人机器上直接 FileNotFoundError。首选保持原样，不改语义。
_CAND = [os.path.join(BC, d, "lingtaios.exe") for d in ("release_pkg", "dist")]
EXE = next((p for p in _CAND if os.path.isfile(p)), _CAND[0])
DN = subprocess.DEVNULL
ok_all = True

def rec(n, ok, d=""):
    global ok_all; ok_all = ok_all and ok
    print("[%s] %-40s %s" % ("PASS" if ok else "FAIL", n, d))

def sh(c):
    r = subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (r.stdout or b"").decode("mbcs", errors="replace")

def kill():
    for ln in sh("netstat -ano -p TCP").splitlines():
        p = ln.split()
        if len(p) >= 5 and p[0] == "TCP" and p[3] == "LISTENING" and p[1].endswith(":8765"):
            sh("taskkill /F /PID %s /T" % p[4])
    sh("taskkill /F /IM lingtaios.exe /T"); time.sleep(1.5)

def post(p, payload, t=90):
    req = urllib.request.Request("http://127.0.0.1:8765/" + p,
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=t) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))

def names():
    d = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/data.json", timeout=20).read().decode("utf-8"))
    return d, sorted(p["name"] for p in d["projects"])

kill()
work = tempfile.mkdtemp(prefix="exemgmt_")
shutil.copy2(EXE, os.path.join(work, "lingtaios.exe"))
proj = os.path.join(work, "我的项目")
os.makedirs(os.path.join(proj, "brain"))
io.open(os.path.join(proj, "brain", "00_宪法.md"), "w", encoding="utf-8").write("# c\n")
io.open(os.path.join(proj, "README.md"), "w", encoding="utf-8").write("# r\n")

subprocess.Popen([os.path.join(work, "lingtaios.exe"), "--no-browser"], cwd=work, stdout=DN, stderr=DN)
up = False
for _ in range(150):
    s = socket.socket(); s.settimeout(0.4); up = s.connect_ex(("127.0.0.1", 8765)) == 0; s.close()
    if up: break
    time.sleep(0.4)
rec("exe 起来了", up)

st, r = post("api/project_add", {"path": proj})
rec("exe 里能添加项目", st == 200 and r.get("ok"), "projects_now=%s" % r.get("projects_now"))
d, ns = names()
rec("项目出现在列表", "我的项目" in ns, str(ns)[:80])

before = sorted(os.listdir(proj))
st, r = post("api/project_remove", {"path": proj})
rec("exe 里能移出项目库", st == 200 and r.get("ok"), "how=%s" % r.get("how"))
rec("⛔ 文件一个没动", os.path.isdir(proj) and sorted(os.listdir(proj)) == before, str(before))
d, ns = names()
rec("已从列表消失", "我的项目" not in ns, str(ns)[:80])
rec("已移出的暴露给前端", any(os.path.normcase(e["path"]) == os.path.normcase(proj)
                          for e in d.get("excluded_projects", [])))

st, r = post("api/project_restore", {"path": proj})
d, ns = names()
rec("exe 里能撤销移出", st == 200 and "我的项目" in ns, str(ns)[:80])

st, r = post("api/project_add", {"path": "C:\Windows\System32"})
rec("危险路径在 exe 里也被拒", st == 400, str(r.get("error"))[:34])

kill(); shutil.rmtree(work, ignore_errors=True)
print("\n%s" % ("ALL PASSED" if ok_all else "SOME FAILED"))
