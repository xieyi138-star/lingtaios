# -*- coding: utf-8 -*-
"""工作区模式端到端：浏览 → 设工作区 → 保存 → 项目动态出现（含新建的）"""
import io, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error
BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY, DN = sys.executable, subprocess.DEVNULL
ok_all = True

def rec(n, ok, d=""):
    global ok_all; ok_all = ok_all and ok
    print("[%s] %-42s %s" % ("PASS" if ok else "FAIL", n, d))

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

def post(p, payload, t=90):
    req = urllib.request.Request("http://127.0.0.1:8765/" + p,
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=t) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))

kill()
# 造一个「用户的工作区」：3 个项目，其中一个没有任何 md（旧判据会漏掉它）
bob = tempfile.mkdtemp(prefix="bobws_")
ws = os.path.join(bob, "work"); os.makedirs(ws)
p1 = os.path.join(ws, "with-organs"); os.makedirs(os.path.join(p1, "brain"))
io.open(os.path.join(p1, "brain", "00_宪法.md"), "w", encoding="utf-8").write("# c\n")
p2 = os.path.join(ws, "doc-project"); os.makedirs(p2)
io.open(os.path.join(p2, "notes.md"), "w", encoding="utf-8").write("# n\n")
p3 = os.path.join(ws, "code-no-md"); os.makedirs(p3)          # 零 md，旧判据必漏
io.open(os.path.join(p3, "main.py"), "w", encoding="utf-8").write("x=1\n")
junk = os.path.join(ws, "docs"); os.makedirs(junk)            # 想排掉的
io.open(os.path.join(junk, "a.md"), "w", encoding="utf-8").write("# a\n")

home = tempfile.mkdtemp(prefix="bobhome_")
rf = os.path.join(tempfile.mkdtemp(), "roots.json")
json.dump({"machine_id": "BOB", "roots": {"NEXUS": None, "D": None, "HOME": home},
           "setup_done": False}, io.open(rf, "w", encoding="utf-8"), ensure_ascii=False)

subprocess.Popen([PY, "-X", "utf8", "dashboard.py", "--no-browser", "--roots-file", rf],
                 cwd=BC, stdout=DN, stderr=DN)
up = False
for _ in range(80):
    s = socket.socket(); s.settimeout(0.4); up = s.connect_ex(("127.0.0.1", 8765)) == 0; s.close()
    if up: break
    time.sleep(0.4)
rec("service up", up)

st, r = post("api/browse", {"path": ""})
rec("browse 根层列盘符", st == 200 and r["dirs"], "%s" % [d["path"] for d in r["dirs"]])

st, r = post("api/browse", {"path": ws})
names = sorted(d["name"] for d in r["dirs"])
rec("browse 工作区看到全部子目录", st == 200 and len(r["dirs"]) == 4, "%s" % names)
rec("browse 标出已装六器官", any(d["installed"] for d in r["dirs"]),
    "%s" % [d["name"] for d in r["dirs"] if d["installed"]])
rec("browse 给出候选计数", r.get("child_candidates") is not None, "child_candidates=%s" % r.get("child_candidates"))
crumb = " > ".join(c["name"] for c in r["crumbs"])
rec("browse 面包屑可回溯", len(r["crumbs"]) >= 2, crumb)

st, r = post("api/setup_save", {"workspaces": [ws], "projects": [], "excluded": [junk], "roots": {}})
rec("保存工作区", st == 200 and r.get("ok"), "found=%s" % r.get("found"))

d = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/data.json", timeout=15).read().decode("utf-8"))
names = sorted(p["name"] for p in d["projects"])
rec("三个项目全收（含零 md 的）", all(x in names for x in ("with-organs", "doc-project", "code-no-md")), "%s" % names)
rec("excluded 生效（docs 被排掉）", "docs" not in names)

# 动态性：现在新建一个项目，不改配置，重算后应自动出现
p4 = os.path.join(ws, "brand-new"); os.makedirs(p4)
io.open(os.path.join(p4, "README.md"), "w", encoding="utf-8").write("# new\n")
post("api/refresh", {})
d2 = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/data.json", timeout=15).read().decode("utf-8"))
names2 = sorted(p["name"] for p in d2["projects"])
rec("新建项目自动出现（无需重配）", "brand-new" in names2, "%s" % names2)

saved = json.load(io.open(rf, encoding="utf-8"))
rec("roots.json 结构正确", saved.get("workspaces") == [ws] and saved.get("excluded") == [junk],
    "workspaces=%s excluded=%s" % (len(saved.get("workspaces", [])), len(saved.get("excluded", []))))
rec("真 roots.json 未被污染",
    json.load(io.open(os.path.join(BC, "roots.json"), encoding="utf-8")).get("workspaces") is None)

kill()
for p in (bob, home, os.path.dirname(rf)): shutil.rmtree(p, ignore_errors=True)
print("\n%s" % ("ALL PASSED" if ok_all else "SOME FAILED"))
