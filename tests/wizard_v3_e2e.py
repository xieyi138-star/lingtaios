# -*- coding: utf-8 -*-
"""向导 v3 端到端：像资源管理器一样浏览 + 扫描直接给项目清单"""
import io, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY, DN = sys.executable, subprocess.DEVNULL
ok_all = True


def rec(n, ok, d=""):
    global ok_all
    ok_all = ok_all and ok
    print("[%s] %-44s %s" % ("PASS" if ok else "FAIL", n, d))


def sh(c):
    r = subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (r.stdout or b"").decode("mbcs", errors="replace")


def kill():
    for ln in sh("netstat -ano -p TCP").splitlines():
        p = ln.split()
        if len(p) >= 5 and p[0] == "TCP" and p[3] == "LISTENING" and p[1].endswith(":8765"):
            sh("taskkill /F /PID %s /T" % p[4])
    sh('wmic process where "name=\'python.exe\' and commandline like \'%%dashboard.py%%\'" delete')
    time.sleep(1.5)


def post(p, payload, t=120):
    req = urllib.request.Request("http://127.0.0.1:8765/" + p,
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=t) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))


kill()
sand = tempfile.mkdtemp(prefix="v3_")
work = os.path.join(sand, "work")
os.makedirs(work)
for name, kind in (("alpha", "organs"), ("beta", "git"), ("gamma", "plain")):
    p = os.path.join(work, name)
    os.makedirs(p)
    io.open(os.path.join(p, "README.md"), "w", encoding="utf-8").write("# %s\n" % name)
    if kind == "organs":
        os.makedirs(os.path.join(p, "brain"))
        io.open(os.path.join(p, "brain", "00_宪法.md"), "w", encoding="utf-8").write("# c\n")
    elif kind == "git":
        os.makedirs(os.path.join(p, ".git"))
# 当前目录里放几个文件，验证浏览器能像资源管理器一样列文件
io.open(os.path.join(work, "note.txt"), "w", encoding="utf-8").write("hi\n")
io.open(os.path.join(work, "plan.md"), "w", encoding="utf-8").write("# plan\n")

home = tempfile.mkdtemp(prefix="v3h_")
rf = os.path.join(sand, "roots.json")
json.dump({"machine_id": "T", "roots": {"NEXUS": None, "D": None, "HOME": home},
           "setup_done": False}, io.open(rf, "w", encoding="utf-8"), ensure_ascii=False)

subprocess.Popen([PY, "-X", "utf8", "dashboard.py", "--no-browser", "--roots-file", rf],
                 cwd=BC, stdout=DN, stderr=DN)
up = False
for _ in range(80):
    s = socket.socket()
    s.settimeout(0.4)
    up = s.connect_ex(("127.0.0.1", 8765)) == 0
    s.close()
    if up:
        break
    time.sleep(0.4)
rec("service up", up)

st, r = post("api/browse", {"path": ""})
rec("根层 = 我的电脑（列盘符）", st == 200 and r["dirs"], str([d["path"] for d in r["dirs"]]))

st, r = post("api/browse", {"path": work})
rec("浏览能同时列文件夹和文件", st == 200 and len(r["dirs"]) == 3 and len(r.get("files", [])) == 2,
    "dirs=%s files=%s" % ([d["name"] for d in r["dirs"]], [f["name"] for f in r.get("files", [])]))
rec("文件带大小", all("size" in f for f in r.get("files", [])),
    str([(f["name"], f["size"]) for f in r.get("files", [])]))
rec("文件夹标出已装六器官", any(d["installed"] for d in r["dirs"]),
    str([d["name"] for d in r["dirs"] if d["installed"]]))

st, r = post("api/find_projects", {"locations": [sand], "depth": 3})
rec("扫描直接给项目清单（不是工作区）", st == 200 and r.get("groups") is not None,
    "total=%s groups=%s ms=%s" % (r.get("total"), len(r.get("groups", [])), r.get("ms")))
allitems = [it["path"] for g in r.get("groups", []) for it in g["items"]]
rec("三个项目都在清单里",
    all(os.path.join(work, n) in allitems for n in ("alpha", "beta", "gamma")),
    str([os.path.basename(x) for x in allitems]))
inst = [it for g in r.get("groups", []) for it in g["items"] if it["installed"]]
rec("已装六器官被标出", len(inst) == 1 and inst[0]["name"] == "alpha", str([i["name"] for i in inst]))

st, r = post("api/setup_save", {"workspaces": [], "projects": allitems,
                                "excluded": [], "roots": {}})
rec("按清单添加后保存", st == 200 and r.get("ok"), "found=%s" % r.get("found"))
d = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/data.json",
                                      timeout=15).read().decode("utf-8"))
names = sorted(p["name"] for p in d["projects"])
rec("三个项目进驾驶舱", all(n in names for n in ("alpha", "beta", "gamma")), str(names))

# 「整个文件夹都要」= 内部存 workspace，动态
st, r = post("api/setup_save", {"workspaces": [work], "projects": [],
                                "excluded": [], "roots": {}})
newp = os.path.join(work, "delta")
os.makedirs(newp)
io.open(os.path.join(newp, "x.md"), "w", encoding="utf-8").write("# d\n")
post("api/refresh", {})
d2 = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/data.json",
                                       timeout=15).read().decode("utf-8"))
names2 = sorted(p["name"] for p in d2["projects"])
rec("整个文件夹要 → 新建的自动出现", "delta" in names2, str(names2))

real = json.load(io.open(os.path.join(BC, "roots.json"), encoding="utf-8"))
rec("真 roots.json 未被污染", real.get("workspaces") is None and real.get("projects") == [])
realdata = json.load(io.open(os.path.join(BC, "site", "data.json"), encoding="utf-8"))
rec("真 data.json 未被污染", len(realdata["projects"]) == 22,
    "%d 个项目" % len(realdata["projects"]))

kill()
for p in (sand, home):
    shutil.rmtree(p, ignore_errors=True)
print("\n%s" % ("ALL PASSED" if ok_all else "SOME FAILED"))
