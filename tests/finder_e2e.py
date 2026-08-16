# -*- coding: utf-8 -*-
"""验「忘了在哪」这条路：扫一遍能不能把工作区找出来"""
import io, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error
BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY, DN = sys.executable, subprocess.DEVNULL
ok_all = True

def rec(n, ok, d=""):
    global ok_all; ok_all = ok_all and ok
    print("[%s] %-40s %s" % ("PASS" if ok else "FAIL", n, d))

def sh(c):
    r = subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (r.stdout or b"").decode("mbcs", errors="replace")

def kill():
    for ln in sh('netstat -ano -p TCP').splitlines():
        p = ln.split()
        if len(p) >= 5 and p[0] == "TCP" and p[3] == "LISTENING" and p[1].endswith(":8765"):
            sh('taskkill /F /PID %s /T' % p[4])
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
# 造「用户忘了位置」的场景：深处埋一个工作区，里面 3 个项目
root = tempfile.mkdtemp(prefix="lost_")
deep = os.path.join(root, "somewhere", "deeper", "myprojects")
os.makedirs(deep)
for name, kind in (("alpha", "organs"), ("beta", "git"), ("gamma", "eng")):
    p = os.path.join(deep, name); os.makedirs(p)
    io.open(os.path.join(p, "README.md"), "w", encoding="utf-8").write("# %s\n" % name)
    if kind == "organs":
        os.makedirs(os.path.join(p, "brain"))
        io.open(os.path.join(p, "brain", "00_宪法.md"), "w", encoding="utf-8").write("# c\n")
    elif kind == "git":
        os.makedirs(os.path.join(p, ".git"))
    else:
        io.open(os.path.join(p, "package.json"), "w", encoding="utf-8").write("{}\n")
# 干扰项：一个资源目录（一堆同类子目录，无任何信号）
res = os.path.join(root, "somewhere", "assets")
os.makedirs(res)
for i in range(12):
    d = os.path.join(res, "clip_%02d" % i); os.makedirs(d)
    io.open(os.path.join(d, "a.md"), "w", encoding="utf-8").write("x\n")

home = tempfile.mkdtemp(prefix="h_")
rf = os.path.join(tempfile.mkdtemp(), "roots.json")
json.dump({"machine_id": "T", "roots": {"NEXUS": None, "D": None, "HOME": home},
           "setup_done": False}, io.open(rf, "w", encoding="utf-8"), ensure_ascii=False)
subprocess.Popen([PY, "-X", "utf8", "dashboard.py", "--no-browser", "--roots-file", rf],
                 cwd=BC, stdout=DN, stderr=DN)
up = False
for _ in range(80):
    s = socket.socket(); s.settimeout(0.4); up = s.connect_ex(("127.0.0.1", 8765)) == 0; s.close()
    if up: break
    time.sleep(0.4)
rec("service up", up)

st, r = post("api/find_projects", {"locations": [root], "depth": 4})
groups = r.get("groups", [])
parents = [g["parent"] for g in groups]
rec("找到埋在深处的工作区", st == 200 and deep in parents,
    "%s ms，共 %s 个候选项目，分组 %s"
    % (r.get("ms"), r.get("total"), [os.path.basename(x) or x for x in parents]))
rec("正确的排第一", groups and groups[0]["parent"] == deep,
    "第一组=%s 里面 %s 个 已装%s"
    % (os.path.basename(groups[0]["parent"]) if groups else "-",
       groups[0]["count"] if groups else 0,
       groups[0]["installed_n"] if groups else 0))
rec("三个项目都在清单里",
    all(any(it["name"] == n for g in groups for it in g["items"]) for n in ("alpha", "beta", "gamma")),
    "%s" % sorted(it["name"] for g in groups for it in g["items"]))
rec("资源目录被排除（12 个 clip 无信号）", res not in parents)

st, r2 = post("api/setup_save", {"workspaces": [deep], "projects": [], "excluded": [], "roots": {}})
d = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/data.json", timeout=15).read().decode("utf-8"))
names = sorted(p["name"] for p in d["projects"])
rec("设为工作区后三个项目都进来", all(x in names for x in ("alpha", "beta", "gamma")), "%s" % names)

st, r3 = post("api/find_projects", {"locations": ["Z:\nope"], "depth": 3})
rec("守卫：不存在的位置", st == 400)

kill()
for p in (root, home, os.path.dirname(rf)): shutil.rmtree(p, ignore_errors=True)
print("\n%s" % ("ALL PASSED" if ok_all else "SOME FAILED"))
