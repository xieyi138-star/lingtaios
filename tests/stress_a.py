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
    # ⛔ 别再把并发实例的输出丢进 DEVNULL。
    #    这条用例间歇性红（exits 里偶尔混一个 1），而红的时候屏幕上只有一串退出码，
    #    没有任何一个实例说过什么——于是每次都只能靠猜，猜完重跑又不复现。
    #    2026-08-18 为此空转了几轮：手动起 4 个实例复现不出来，因为**手动那次的
    #    输出是留着的，回归这次的没留**。留住现场的成本是几 KB，猜的成本是一整轮。
    #    同坑库 T18：判红那一刻就要有现场，不能指望「等会儿再重跑一遍看看」。
    return subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

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
    # ⛔ 这里以前写死 `total == 59 and ok == 59`。两个毛病：
    #    ① 真源清单只要合法地多一条，它就为**错误的理由**报红，红久了没人看；
    #    ② 59 是某天的快照，写下来那刻就开始烂——跟坑库 expect:38 烂到 42 是同一个病。
    #    该断言的是**不变量**：清单里该在的全在、没有失踪的。
    #    再加一条 applicable > 0 —— 清单解析失败时读数全是 0，0==0 照样"通过"，
    #    那是真空绿（坑库 T13）。
    h = health()
    ok, app_ = h.get("ok"), h.get("applicable")
    rec("1 clean start: 真源清单全绿且没有失踪的",
        isinstance(app_, int) and app_ > 0 and ok == app_
        and not h.get("missing") and not h.get("absent"),
        "ok=%s/applicable=%s total=%s missing=%s absent=%s noroot=%s"
        % (ok, app_, h.get("total"), len(h.get("missing", [])), h.get("absent"), h.get("noroot")))
    BASE_OK = ok
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
    outs = []
    for p in ps:
        try:
            o, _ = p.communicate(timeout=150)
        except subprocess.TimeoutExpired:
            p.kill()
            o = b""
        outs.append((o or b"").decode("utf-8", errors="replace").strip())
    time.sleep(1)
    same = owner_pid(8765) == base_owner
    codes = [p.returncode for p in ps]
    ok4 = same and all(c == 0 for c in codes)
    rec("4 concurrent x4: single owner", ok4,
        "exits=%s owner unchanged=%s" % (codes, same))
    if not ok4:
        # 现场只有这一次，重跑就没了——判红当场打出来（坑库 T18）
        print("      ↳ 并发实例各自说了什么（这段是根因唯一的线索）：")
        for i, (c, o) in enumerate(zip(codes, outs)):
            tail = [ln for ln in o.splitlines() if ln.strip()][-3:]
            print("        [%d] exit=%s  %s" % (i, c, " ⏎ ".join(tail) if tail else "(无输出)"))
    try:
        # 同样不写死数字：跟风暴前那次读到的比，要求「一个都没掉」
        h = health()
        rec("4 survivor healthy after storm",
            isinstance(BASE_OK, int) and BASE_OK > 0 and h.get("ok") == BASE_OK,
            "ok=%s（风暴前 %s）" % (h.get("ok"), BASE_OK))
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
