# -*- coding: utf-8 -*-
"""压测批2：功能、压力、独立性"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request
import concurrent.futures as cf

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
    print("[%s] %-38s %s" % ("PASS" if ok else "FAIL", name, detail))

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

def wait_up(port, secs=60):
    t0 = time.time()
    while time.time() - t0 < secs:
        if listening(port): return True
        time.sleep(0.4)
    return False

def get(path, port=8765, timeout=10):
    with urllib.request.urlopen("http://127.0.0.1:%d/%s" % (port, path), timeout=timeout) as r:
        return r.status, r.read()

def post(path, payload, port=8765, timeout=20):
    req = urllib.request.Request("http://127.0.0.1:%d/%s" % (port, path),
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))

killall()

# ---- 6. exe copied to a clean dir, no roots.json (simulates a user download) ----
tmp = tempfile.mkdtemp(prefix="lt_fresh_")
shutil.copy2(EXE, os.path.join(tmp, "lingtaios.exe"))
fresh = os.path.join(tmp, "lingtaios.exe")
rec("6 fresh dir has no roots.json", not os.path.exists(os.path.join(tmp, "roots.json")), tmp)
subprocess.Popen([fresh, "--no-browser"], cwd=tmp, stdout=DN, stderr=DN)
up = wait_up(8765, 60)
rec("6 fresh download: starts", up, "8765 up" if up else "TIMEOUT 60s")
if up:
    made = os.path.exists(os.path.join(tmp, "roots.json"))
    rec("6 fresh download: self-provisions roots.json", made,
        open(os.path.join(tmp, "roots.json"), encoding="utf-8").read().replace("\n", " ")[:90] if made else "NOT created")
    st, body = get("data.json")
    h = json.loads(body.decode("utf-8")).get("health", {})
    rec("6 fresh download: healthy", st == 200 and h.get("ok") == h.get("total") and not h.get("missing"),
        "HTTP %s total=%s ok=%s missing=%s" % (st, h.get("total"), h.get("ok"), len(h.get("missing", []))))

    # ---- 7. route coverage on the fresh instance ----
    routes_ok = []
    for p in ("", "data.json", "style.css", "app.js", "index.html"):
        try:
            st, b = get(p)
            routes_ok.append((p or "/", st, len(b)))
        except Exception as e:
            routes_ok.append((p or "/", "ERR", repr(e)[:40]))
    rec("7 GET routes", all(r[1] == 200 for r in routes_ok), str(routes_ok))

    try:
        st, d = post("api/templates", {})
        rec("7 POST api/templates", st == 200, "HTTP %s keys=%s" % (st, list(d)[:4]))
    except Exception as e:
        rec("7 POST api/templates", False, repr(e)[:60])
    try:
        st, d = post("api/project_detail", {"path": BC})
        rec("7 POST api/project_detail", st == 200 and d.get("ok"), "HTTP %s ok=%s organs=%s" % (st, d.get("ok"), len(d.get("organs", {}))))
    except Exception as e:
        rec("7 POST api/project_detail", False, repr(e)[:60])
    try:
        st, d = post("api/project_detail", {"path": r"C:\..\..\evil"})
        rec("7 path traversal rejected", st >= 400 or not d.get("ok"), "HTTP %s ok=%s err=%s" % (st, d.get("ok"), str(d.get("error"))[:34]))
    except urllib.error.HTTPError as e:
        rec("7 path traversal rejected", e.code >= 400, "HTTP %s" % e.code)
    except Exception as e:
        rec("7 path traversal rejected", False, repr(e)[:60])

    # ---- 8. concurrency ----
    def hit(i):
        try:
            st, b = get("data.json", timeout=25)
            return st == 200 and len(b) > 1000
        except Exception:
            return False
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=50) as ex:
        got = list(ex.map(hit, range(200)))
    dt = time.time() - t0
    rec("8 concurrency 200 req / 50 threads", all(got),
        "%d/%d ok in %.1fs (%.0f req/s)" % (sum(got), len(got), dt, len(got)/dt))

    def hit_detail(i):
        try:
            st, d = post("api/project_detail", {"path": BC}, timeout=40)
            return st == 200 and d.get("ok")
        except Exception:
            return False
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=20) as ex:
        got2 = list(ex.map(hit_detail, range(60)))
    dt = time.time() - t0
    rec("8 concurrency 60 heavy POST / 20 thr", all(got2),
        "%d/%d ok in %.1fs" % (sum(got2), len(got2), dt))

    # still alive?
    try:
        st, _ = get("data.json"); rec("8 alive after load", st == 200, "HTTP %s" % st)
    except Exception as e:
        rec("8 alive after load", False, repr(e)[:60])

killall()
try: shutil.rmtree(tmp, ignore_errors=True)
except Exception: pass

# ---- 9. exe --selftest and --health survive packaging ----
r = subprocess.run([EXE, "--selftest"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
out = (r.stdout or b"").decode("mbcs", errors="replace")
nok = out.count("ok ")
rec("9 exe --selftest", r.returncode == 0 and nok >= 15, "exit=%d, %d checks ok" % (r.returncode, nok))

r = subprocess.run([EXE, "--health"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
out2 = (r.stdout or b"").decode("mbcs", errors="replace")
rec("9 exe --health", r.returncode == 0, "exit=%d :: %s" % (r.returncode, out2.strip().replace("\n", " | ")[:110]))

print("\n" + "=" * 66)
bad = [n for n, ok, _ in results if not ok]
print("BATCH B: %d/%d passed" % (len(results) - len(bad), len(results)))
if bad:
    for n in bad: print("  FAILED:", n)
