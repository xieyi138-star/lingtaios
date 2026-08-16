# -*- coding: utf-8 -*-
"""压测批1：启动语义与端口竞争"""
import json, os, socket, subprocess, sys, time, urllib.request

BC  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# release_pkg 是作者本机的发布目录，别人 clone 下来只有自己打出来的 dist——两个都认，
# 谁在就用谁，否则这行在别人机器上直接 FileNotFoundError。首选保持原样，不改语义。
_CAND = [os.path.join(BC, d, "lingtaios.exe") for d in ("dist", "release_pkg")]
EXE = next((p for p in _CAND if os.path.isfile(p)), _CAND[0])
PY  = sys.executable
DN  = subprocess.DEVNULL
results = []

def rec(name, ok, detail):
    results.append((name, ok, detail))
    print("[%s] %-36s %s" % ("PASS" if ok else "FAIL", name, detail))

def sh(cmd):
    r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (r.stdout or b"").decode("mbcs", errors="replace")

def killall():
    sh('taskkill /F /IM lingtaios.exe /T')
    sh('wmic process where "name=\'python.exe\' and commandline like \'%%dashboard.py%%\'" delete')
    time.sleep(1.5)

def listening(port):
    s = socket.socket(); s.settimeout(0.4)
    try: return s.connect_ex(("127.0.0.1", port)) == 0
    finally: s.close()

def owner_pid(port):
    for ln in sh('netstat -ano -p TCP').splitlines():
        p = ln.split()
        if len(p) >= 5 and p[0] == "TCP" and p[1].endswith(":%d" % port) and p[3] == "LISTENING":
            return p[4]
    return None

def health(port=8765):
    with urllib.request.urlopen("http://127.0.0.1:%d/data.json" % port, timeout=8) as r:
        return json.loads(r.read().decode("utf-8")).get("health", {})

def spawn(cmd, cwd):
    return subprocess.Popen(cmd, cwd=cwd, stdout=DN, stderr=DN)

def run(cmd, cwd=None, timeout=120):
    r = subprocess.run(cmd, cwd=cwd, stdout=DN, stderr=DN, timeout=timeout)
    return r.returncode

def wait_up(port, secs=45):
    t0 = time.time()
    while time.time() - t0 < secs:
        if listening(port): return True
        time.sleep(0.4)
    return False

killall()

# 1. clean start
spawn([EXE, "--no-browser"], os.path.dirname(EXE))
up = wait_up(8765)
rec("1 clean start: port up", up, "8765 listening" if up else "TIMEOUT")
base_owner = None
if up:
    h = health()
    rec("1 clean start: 59/59 real green",
        h.get("total") == 59 and h.get("ok") == 59 and not h.get("missing"),
        "total=%s ok=%s missing=%s noroot=%s" % (h.get("total"), h.get("ok"), len(h.get("missing", [])), h.get("noroot")))
    base_owner = owner_pid(8765)
    rec("1 owner pid captured", base_owner is not None, "pid=%s" % base_owner)

    # 2. exe vs exe
    t0 = time.time(); c = run([EXE, "--no-browser"]); dt = time.time() - t0
    same = owner_pid(8765) == base_owner
    rec("2 exe vs exe: yields", c == 0 and dt < 60 and same,
        "exit=%d in %.1fs, owner unchanged=%s" % (c, dt, same))

    # 3. python source vs exe
    t0 = time.time(); c = run([PY, "-X", "utf8", "dashboard.py", "--no-browser"], cwd=BC); dt = time.time() - t0
    same = owner_pid(8765) == base_owner
    rec("3 python vs exe: yields", c == 0 and same,
        "exit=%d in %.1fs, owner unchanged=%s" % (c, dt, same))

    # 4. 4-way concurrent race
    ps = [spawn([EXE, "--no-browser"], os.path.dirname(EXE)) for _ in range(4)]
    for p in ps:
        try: p.wait(timeout=150)
        except subprocess.TimeoutExpired: p.kill()
    time.sleep(1)
    same = owner_pid(8765) == base_owner
    codes = [p.returncode for p in ps]
    rec("4 concurrent x4: single owner", same and all(c == 0 for c in codes),
        "exits=%s owner unchanged=%s" % (codes, same))
    try:
        h = health(); rec("4 survivor healthy after storm", h.get("ok") == 59, "ok=%s" % h.get("ok"))
    except Exception as e:
        rec("4 survivor healthy after storm", False, repr(e))

killall()

# 5. non-lingtai squatter on 8765 -> must fall through to 8766
squat = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
squat.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
squat.bind(("127.0.0.1", 8765)); squat.listen(5)
spawn([EXE, "--no-browser"], os.path.dirname(EXE))
up = wait_up(8766, 45)
d = "8766 listening" if up else "did NOT fall through"
if up:
    try:
        h = health(8766); d += ", ok=%s/%s" % (h.get("ok"), h.get("total"))
    except Exception as e:
        d += ", data.json FAILED %r" % e
rec("5 squatter on 8765 -> uses 8766", up, d)
squat.close()
killall()

print("\n" + "=" * 64)
bad = [n for n, ok, _ in results if not ok]
print("BATCH A: %d/%d passed" % (len(results) - len(bad), len(results)))
if bad: print("FAILED:", bad)
