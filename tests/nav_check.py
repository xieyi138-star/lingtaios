# -*- coding: utf-8 -*-
"""确认 exe 里侧栏确实是「项目库」——改的是打包进去的那份 web/，不是本地的"""
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
    sh("taskkill /F /IM lingtaios.exe /T"); time.sleep(1.5)

kill()
work = tempfile.mkdtemp(prefix="nav_")
shutil.copy2(EXE, os.path.join(work, "lingtaios.exe"))
subprocess.Popen([os.path.join(work, "lingtaios.exe"), "--no-browser"], cwd=work, stdout=DN, stderr=DN)
for _ in range(150):
    s = socket.socket(); s.settimeout(0.4); up = s.connect_ex(("127.0.0.1", 8765)) == 0; s.close()
    if up: break
    time.sleep(0.4)

html = urllib.request.urlopen("http://127.0.0.1:8765/", timeout=15).read().decode("utf-8")
appjs = urllib.request.urlopen("http://127.0.0.1:8765/app.js", timeout=15).read().decode("utf-8")

checks = [
    ("侧栏是「项目库」", 'data-page="projects">项目库</button>' in html),
    ("侧栏不再是「项目」", 'data-page="projects">项目</button>' not in html),
    ("首页仍是「首页」", 'data-page="home">首页</button>' in html),
    ("页面标题「项目库（N）」", "项目库（" in appjs),
    # 断言过期了一轮：文案早改成「去项目库看，全部可点开续做 →」，这条还找旧串，
    # 于是 nav_check 一直红着没人管。测试跟着文案走，别让红灯变成背景噪音。
    ("首页指路文案已同步", "去项目库看，全部可点开续做" in appjs),
    ("空状态文案一致", "项目库还是空的" in appjs),
    ("移出按钮文案一致", "移出项目库" in appjs),
    # 判据强度这一节是只读提示，绝不能混进那些「勾选删除」的清单里——
    # 混进去等于告诉人「把判据弱的坑删掉」，正好判反（该改判据，不是删坑）。
    ("进化审计有判据强度小节", "失效判据的强度" in appjs),
    ("判据强度是只读的（没有勾选框）",
     "失效判据的强度" in appjs and 'data-kind="grade"' not in appjs),
]
for n, ok in checks:
    print("[%s] %s" % ("PASS" if ok else "FAIL", n))
kill(); shutil.rmtree(work, ignore_errors=True)
print("\n%s" % ("ALL PASSED" if all(o for _, o in checks) else "SOME FAILED"))
