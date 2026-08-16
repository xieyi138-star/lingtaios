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
real_roots = os.path.join(BC, "roots.json")
real_data = os.path.join(BC, "site", "data.json")
before = (md5(real_roots), md5(real_data))
print("演练前 roots.json=%s data.json=%s" % (before[0][:8], before[1][:8]))

# 造演练环境
sand = tempfile.mkdtemp(prefix="drill_")
ws = os.path.join(sand, "work")
os.makedirs(os.path.join(ws, "p1", "brain"))
io.open(os.path.join(ws, "p1", "brain", "00_宪法.md"), "w", encoding="utf-8").write("# c\n")
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

# 做几个会写产物的动作
for path, payload in (("api/setup_save", {"workspaces": [ws], "projects": [], "excluded": [], "roots": {}}),
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

after = (md5(real_roots), md5(real_data))
print("\n演练后 roots.json=%s data.json=%s" % (after[0][:8], after[1][:8]))
print("真 roots.json  未被碰:", "PASS" if before[0] == after[0] else "FAIL")
print("真 data.json   未被碰:", "PASS" if before[1] == after[1] else "FAIL")
drill_site = os.path.join(sand, "site", "data.json")
print("演练产物落在演练目录:", "PASS" if os.path.isfile(drill_site) else "FAIL (%s)" % drill_site)
real = json.load(io.open(real_data, encoding="utf-8"))
print("真 data.json 仍是 %d 个项目" % len(real["projects"]))
for p in (sand, home):
    shutil.rmtree(p, ignore_errors=True)
