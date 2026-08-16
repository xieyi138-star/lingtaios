# -*- coding: utf-8 -*-
"""后端去重兜底 + 选择器数据源 e2e"""
import io, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY, DN = sys.executable, subprocess.DEVNULL
ok_all = True


def rec(n, ok, d=""):
    global ok_all
    ok_all = ok_all and ok
    print("[%s] %-46s %s" % ("PASS" if ok else "FAIL", n, d))


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
sand = tempfile.mkdtemp(prefix="dedup_")
work = os.path.join(sand, "work")
os.makedirs(work)
for n in ("a", "b", "c"):
    p = os.path.join(work, n)
    os.makedirs(p)
    io.open(os.path.join(p, "README.md"), "w", encoding="utf-8").write("# %s\n" % n)
outside = os.path.join(sand, "outside")
os.makedirs(outside)
io.open(os.path.join(outside, "x.md"), "w", encoding="utf-8").write("# x\n")

home = tempfile.mkdtemp(prefix="dh_")
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

# 选择器的数据源：browse 能列文件夹+文件+已装标记
st, r = post("api/browse", {"path": work})
rec("选择器数据源可用", st == 200 and len(r["dirs"]) == 3,
    "dirs=%s files=%s" % ([d["name"] for d in r["dirs"]], len(r.get("files", []))))
rec("给出「里面有几个」用于整folder选项", r.get("child_candidates") == 3,
    "child_candidates=%s" % r.get("child_candidates"))

# 后端去重兜底：故意把「被工作区罩住的」也塞进 projects
st, r = post("api/setup_save", {
    "workspaces": [work],
    "projects": [os.path.join(work, "a"), os.path.join(work, "b"), outside, outside],
    "excluded": [], "roots": {}})
saved = json.load(io.open(rf, encoding="utf-8"))
rec("保存成功", st == 200 and r.get("ok"))
rec("被工作区罩住的已从 projects 剔除",
    all(not p.lower().startswith(work.lower() + os.sep) for p in saved["projects"]),
    "projects=%s" % [os.path.basename(p) for p in saved["projects"]])
rec("重复项被去掉", len(saved["projects"]) == len(set(saved["projects"])) == 1,
    "%s" % saved["projects"])
rec("工作区照常保留", saved["workspaces"] == [work])

d = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/data.json",
                                      timeout=15).read().decode("utf-8"))
names = sorted(p["name"] for p in d["projects"])
rec("驾驶舱里 a/b/c/outside 都在且各一份",
    names.count("a") == 1 and names.count("outside") == 1 and "c" in names, str(names))

real = json.load(io.open(os.path.join(BC, "roots.json"), encoding="utf-8"))
rec("真 roots.json 未被污染", real.get("workspaces") is None)
realdata = json.load(io.open(os.path.join(BC, "site", "data.json"), encoding="utf-8"))
rec("真 data.json 未被污染", len(realdata["projects"]) == 22,
    "%d 个项目" % len(realdata["projects"]))

kill()
for p in (sand, home):
    shutil.rmtree(p, ignore_errors=True)
print("\n%s" % ("ALL PASSED" if ok_all else "SOME FAILED"))
