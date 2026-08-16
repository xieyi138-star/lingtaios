# -*- coding: utf-8 -*-
"""验 api/pick_folder：起真服务 → 调 API → 对话框弹出 → 自动按 ENTER → 拿到路径"""
import ctypes, ctypes.wintypes as wt, json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY, DN = sys.executable, subprocess.DEVNULL
user32 = ctypes.windll.user32
EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
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
    sh('wmic process where "name=\'python.exe\' and commandline like \'%%dashboard.py%%\'" delete')
    time.sleep(1.5)

def dialogs():
    hits = []
    def cb(h, _):
        if user32.IsWindowVisible(h):
            c = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(h, c, 64)
            if c.value == "#32770":
                hits.append(h)
        return True
    user32.EnumWindows(EnumProc(cb), 0)
    return hits

kill()
sand = tempfile.mkdtemp(prefix="np_")
home = tempfile.mkdtemp(prefix="nph_")
rf = os.path.join(sand, "roots.json")
json.dump({"machine_id": "T", "roots": {"NEXUS": None, "D": None, "HOME": home},
           "setup_done": False}, open(rf, "w", encoding="utf-8"))
subprocess.Popen([PY, "-X", "utf8", "dashboard.py", "--no-browser", "--roots-file", rf],
                 cwd=BC, stdout=DN, stderr=DN)
up = False
for _ in range(80):
    s = socket.socket(); s.settimeout(0.4); up = s.connect_ex(("127.0.0.1", 8765)) == 0; s.close()
    if up: break
    time.sleep(0.4)
rec("service up", up)

state = {}
def watchdog():
    for _ in range(30):
        time.sleep(0.4)
        h = dialogs()
        if h:
            state["popped"] = True
            state["foreground"] = (user32.GetForegroundWindow() == h[0])
            time.sleep(0.4)
            user32.PostMessageW(h[0], 0x0100, 0x0D, 0)
            user32.PostMessageW(h[0], 0x0101, 0x0D, 0)
            return
    state["popped"] = False

threading.Thread(target=watchdog, daemon=True).start()
req = urllib.request.Request("http://127.0.0.1:8765/api/pick_folder",
                             data=json.dumps({"title": "选择项目所在的文件夹"}).encode("utf-8"),
                             headers={"Content-Type": "application/json"})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=40) as r:
        res = json.loads(r.read().decode("utf-8"))
except Exception as e:
    res = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
dt = time.time() - t0

rec("对话框确实弹出", state.get("popped") is True)
rec("弹出即在最前（不藏在浏览器后）", state.get("foreground") is True)
rec("API 返回成功", res.get("ok") is True, str(res)[:110])
rec("拿到真实路径", isinstance(res.get("path"), str) and os.path.isdir(res.get("path") or ""),
    "%s（%.1fs）" % (res.get("path"), dt))
rec("附带证据字段", "installed" in res and "child_candidates" in res,
    "installed=%s child=%s" % (res.get("installed"), res.get("child_candidates")))
rec("无残留对话框", not dialogs())

kill()
for p in (sand, home): shutil.rmtree(p, ignore_errors=True)
print("\n%s" % ("ALL PASSED" if ok_all else "SOME FAILED"))
