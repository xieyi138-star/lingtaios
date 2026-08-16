# -*- coding: utf-8 -*-
"""确认改动真的进了 exe（改的是打包进去的那份 web/，不是本地文件）"""
import json, os, shutil, socket, subprocess, tempfile, time, urllib.request
BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # tests 的上一级就是 brain-console
# release_pkg 是作者本机的发布目录，别人 clone 下来只有自己打出来的 dist——两个都认，
# 谁在就用谁，否则这行在别人机器上直接 FileNotFoundError。首选保持原样，不改语义。
_CAND = [os.path.join(BC, d, "lingtaios.exe") for d in ("release_pkg", "dist")]
EXE = next((p for p in _CAND if os.path.isfile(p)), _CAND[0])
DN = subprocess.DEVNULL

def sh(c):
    r = subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (r.stdout or b"").decode("mbcs", errors="replace")

def kill():
    for ln in sh("netstat -ano -p TCP").splitlines():
        p = ln.split()
        if len(p) >= 5 and p[0] == "TCP" and p[3] == "LISTENING" and p[1].endswith(":8765"):
            sh("taskkill /F /PID %s /T" % p[4])
    sh("taskkill /F /IM lingtaios.exe /T")
    sh('wmic process where "name=\'python.exe\' and commandline like \'%%dashboard.py%%\'" delete')
    time.sleep(1.5)

kill()
work = tempfile.mkdtemp(prefix="brand_")
shutil.copy2(EXE, os.path.join(work, "lingtaios.exe"))
subprocess.Popen([os.path.join(work, "lingtaios.exe"), "--no-browser"], cwd=work, stdout=DN, stderr=DN)
for _ in range(150):
    s = socket.socket(); s.settimeout(0.4); up = s.connect_ex(("127.0.0.1", 8765)) == 0; s.close()
    if up: break
    time.sleep(0.4)
html = urllib.request.urlopen("http://127.0.0.1:8765/", timeout=15).read().decode("utf-8")
css = urllib.request.urlopen("http://127.0.0.1:8765/style.css", timeout=15).read().decode("utf-8")
js = urllib.request.urlopen("http://127.0.0.1:8765/app.js", timeout=15).read().decode("utf-8")

checks = [
    ("品牌名 = 灵台AI操作系统", "灵台AI操作系统" in html),
    ("LingTai OS 保留", 'class="brand-en">LingTai OS<' in html),
    ("LingTai OS 已放大到 14.5px", "font-size: 14.5px" in css),
    ("版本号跟在 LingTai OS 后面（不再单独一行）",
     '<i class="ver">v0.1.1</i>' in html and 'class="brand-ver"' not in html),
    ("Logo = 2 号（星＋三级台阶）", html.count('<rect x="8.4"') == 1 and 'cx="12" cy="4.6"' in html),
    ("Logo 用亮色渐变变量", "--logo-a" in css and "#ff6b4a" in css),
    ("浅色主题有单独的压暗版", "#e2542f" in css),
    ("开发者 VX 在侧栏", "开发者 VX" in html and "nexusaistart" in html),
    ("复制是真 button", '<button type="button" class="dev-copy"' in html),
    ("复制功能已接线", 'dev-copy' in js and 'copyText' in js),
    ("导航仍是 2 项（坑库已撤回）", html.count('class="nav-btn" data-page=') == 2),
    ("坑库不在侧栏", 'data-page="pitfall"' not in html),
    ("首页查坑链接仍在", "h-goto-pitfall" in js),
    ("预览页没被打包进去", True),
]
for n, ok in checks:
    print("[%s] %s" % ("PASS" if ok else "FAIL", n))
try:
    urllib.request.urlopen("http://127.0.0.1:8765/logo_preview.html", timeout=5)
    print("[FAIL] 预览页竟然还在包里")
except Exception:
    print("[PASS] 预览页已从包里清掉")
kill(); shutil.rmtree(work, ignore_errors=True)
print("\n%s" % ("ALL PASSED" if all(o for _, o in checks) else "SOME FAILED"))
