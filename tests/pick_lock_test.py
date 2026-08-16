# -*- coding: utf-8 -*-
"""单验并发保护：对话框开着时再点「添加项目」，必须被拒（409），不许弹出第二个"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # tests 的上一级就是 brain-console
# release_pkg 是作者本机的发布目录，别人 clone 下来只有自己打出来的 dist——两个都认，
# 谁在就用谁，否则这行在别人机器上直接 FileNotFoundError。首选保持原样，不改语义。
_CAND = [os.path.join(BC, d, "lingtaios.exe") for d in ("release_pkg", "dist")]
EXE = next((p for p in _CAND if os.path.isfile(p)), _CAND[0])
DN = subprocess.DEVNULL
user32 = ctypes.windll.user32
EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def sh(c):
    r = subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (r.stdout or b"").decode("mbcs", errors="replace")


def kill():
    for ln in sh("netstat -ano -p TCP").splitlines():
        p = ln.split()
        if len(p) >= 5 and p[0] == "TCP" and p[3] == "LISTENING" and p[1].endswith(":8765"):
            sh("taskkill /F /PID %s /T" % p[4])
    sh("taskkill /F /IM lingtaios.exe /T")
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


def call(out, key):
    req = urllib.request.Request("http://127.0.0.1:8765/api/pick_folder", data=b"{}",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out[key] = (r.status, json.loads(r.read().decode("utf-8")))
    except urllib.error.HTTPError as e:
        out[key] = (e.code, json.loads(e.read().decode("utf-8", "replace")))
    except Exception as e:
        out[key] = ("ERR", str(e))


kill()
work = tempfile.mkdtemp(prefix="lock_")
shutil.copy2(EXE, os.path.join(work, "lingtaios.exe"))
subprocess.Popen([os.path.join(work, "lingtaios.exe"), "--no-browser"],
                 cwd=work, stdout=DN, stderr=DN)
for _ in range(150):
    s = socket.socket()
    s.settimeout(0.4)
    up = s.connect_ex(("127.0.0.1", 8765)) == 0
    s.close()
    if up:
        break
    time.sleep(0.4)
print("exe up:", up)

out = {}
t1 = threading.Thread(target=call, args=(out, "first"))
t1.start()

# 等第一个对话框真的出现，再发第二个请求
for _ in range(40):
    time.sleep(0.3)
    if dialogs():
        break
n_before = len(dialogs())
print("第一个请求已弹出对话框数:", n_before)

t2 = threading.Thread(target=call, args=(out, "second"))
t2.start()
t2.join(timeout=30)
n_after = len(dialogs())
print("第二个请求发出后对话框数:", n_after)

# 收尾：关掉第一个
for h in dialogs():
    user32.PostMessageW(h, 0x0100, 0x1B, 0)   # ESC = 取消
    user32.PostMessageW(h, 0x0101, 0x1B, 0)
t1.join(timeout=30)

code2 = out.get("second", (None,))[0]
print()
print("[%s] 第二次点击被拒        second=%s" % ("PASS" if code2 == 409 else "FAIL", out.get("second")))
print("[%s] 没有弹出第二个对话框    %d -> %d" % ("PASS" if n_after == n_before else "FAIL", n_before, n_after))
print("[%s] 第一个请求正常收尾      first=%s" % (
    "PASS" if out.get("first", (None,))[0] == 200 else "FAIL", str(out.get("first"))[:80]))
print("[%s] 无残留对话框" % ("PASS" if not dialogs() else "FAIL"))

kill()
shutil.rmtree(work, ignore_errors=True)
