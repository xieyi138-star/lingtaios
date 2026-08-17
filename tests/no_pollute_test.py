# -*- coding: utf-8 -*-
"""验：演练（--roots-file）绝不碰真 roots.json 与真 site/data.json"""
import hashlib, io, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY, DN = sys.executable, subprocess.DEVNULL

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

def md5(p):
    return hashlib.md5(io.open(p, "rb").read()).hexdigest()

kill()
# 布局判定跟 spec/install/dashboard 同一条：同级有 project-delivery = 摊平的发布仓
SKILLS = BC if os.path.isdir(os.path.join(BC, "project-delivery")) else os.path.dirname(BC)
real_roots = os.path.join(BC, "roots.json")
real_data = os.path.join(BC, "site", "data.json")
# ⛔ 第三样真源：装配图。api_install_organs 会往里追加 L6 登记行，
#    而「演练不许碰真源」以前只堵了配置和产物——实测演练跑 4 次，
#    真装配图里就多了 4 条指向临时目录的死登记，健康检查 absent 从 0 变 4。
real_map = os.path.join(SKILLS, "project-delivery", "装配图.md")
before = (md5(real_roots), md5(real_data), md5(real_map))
print("演练前 roots.json=%s data.json=%s 装配图=%s"
      % (before[0][:8], before[1][:8], before[2][:8]))

# 造演练环境
sand = tempfile.mkdtemp(prefix="drill_")
ws = os.path.join(sand, "work")
os.makedirs(os.path.join(ws, "p1", "brain"))
io.open(os.path.join(ws, "p1", "brain", "00_宪法.md"), "w", encoding="utf-8").write("# c\n")
# p2 没有 brain：给 install_organs 用，那是唯一会写装配图的入口
os.makedirs(os.path.join(ws, "p2"))
io.open(os.path.join(ws, "p2", "README.md"), "w", encoding="utf-8").write("# p2\n")
home = tempfile.mkdtemp(prefix="dh_")
rf = os.path.join(sand, "roots.json")
json.dump({"machine_id": "DRILL", "roots": {"NEXUS": None, "D": None, "HOME": home},
           "setup_done": False}, io.open(rf, "w", encoding="utf-8"), ensure_ascii=False)

subprocess.Popen([PY, "-X", "utf8", "dashboard.py", "--no-browser", "--roots-file", rf],
                 cwd=BC, stdout=DN, stderr=DN)
up = False
for _ in range(80):
    s = socket.socket(); s.settimeout(0.4)
    up = s.connect_ex(("127.0.0.1", 8765)) == 0; s.close()
    if up: break
    time.sleep(0.4)
print("演练服务起来:", up)

# 做几个会写产物的动作（install_organs 是唯一会写装配图的，不放它进来就等于没验那一条）
for path, payload in (("api/setup_save", {"workspaces": [ws], "projects": [], "excluded": [], "roots": {}}),
                      ("api/install_organs", {"path": os.path.join(ws, "p2")}),
                      ("api/refresh", {})):
    req = urllib.request.Request("http://127.0.0.1:8765/" + path,
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=90).read()
    except Exception as e:
        print("  %s -> %s" % (path, type(e).__name__))

d = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/data.json", timeout=20).read().decode("utf-8"))
print("演练里看到的项目:", sorted(p["name"] for p in d["projects"]))
kill()

after = (md5(real_roots), md5(real_data), md5(real_map))
print("\n演练后 roots.json=%s data.json=%s 装配图=%s"
      % (after[0][:8], after[1][:8], after[2][:8]))

drill_site = os.path.join(sand, "site", "data.json")
drill_map = os.path.join(sand, "装配图.演练.md")
real = json.load(io.open(real_data, encoding="utf-8"))

# ⛔ 以前这里只 print("FAIL")，既不打 [FAIL] 也不设退出码——而 run_all 判红看的正是
#    这两样。也就是说：**守「不许碰真源」这条红线的测试，自己红了会被判成绿。**
#    跟「跳过 return 0 被判绿」是同一个病。检查项统一收口，最后按结果退出。
checks = [
    ("真 roots.json 未被碰", before[0] == after[0]),
    ("真 data.json 未被碰", before[1] == after[1]),
    ("真 装配图.md 未被碰", before[2] == after[2]),
    ("演练产物落在演练目录（site/data.json）", os.path.isfile(drill_site)),
    ("演练的装配图登记也落在演练目录", os.path.isfile(drill_map)),
]
for name, ok in checks:
    print("[%s] %s" % ("PASS" if ok else "FAIL", name))
print("真 data.json 仍是 %d 个项目" % len(real["projects"]))
for p in (sand, home):
    shutil.rmtree(p, ignore_errors=True)
bad = [n for n, o in checks if not o]
print("\n%s" % ("ALL PASSED" if not bad else "SOME FAILED：" + "、".join(bad)))
sys.exit(1 if bad else 0)
