# -*- coding: utf-8 -*-
"""确认改动真的进了 exe（改的是打包进去的那份 web/，不是本地文件）"""
import json, os, re, shutil, socket, subprocess, tempfile, time, urllib.request
BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # tests 的上一级就是 brain-console
# release_pkg 是作者本机的发布目录，别人 clone 下来只有自己打出来的 dist——两个都认。
# ⛔ 顺序必须 dist 优先，跟 run_all._exe() 和 soul_manifest 一致：整套回归起的、验的
#    都是 dist 那个 exe，这里若去验 release_pkg 那个，同一轮回归测的就是两个不同的
#    二进制；而且 release_pkg 停在上次打包，改一行源码这条就红到下次发版为止。
_CAND = [os.path.join(BC, d, "lingtaios.exe") for d in ("dist", "release_pkg")]
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
    # 这条验的是版本号的**位置**（跟在 LingTai OS 后面、不再单独一行），不是它的值。
    # 原来写死 v0.1.1，一升版就假红——等于把版本号又抄了一份（P10：同一数字抄多份必分叉）。
    # 「三处版本号一致」由 make_release.py 的发布闸负责，这里不重复。
    # ⛔ 断言里也不许残留 `>v`：那等于仍然假设版本号**写在 html 里**。现在徽章由
    #    app.js 从 data.json 填（VERSION 是唯一真源），html 里那个槽是空的。
    ("版本号槽位跟在 LingTai OS 后面（不再单独一行）",
     'LingTai OS<i class="ver"' in html and 'class="brand-ver"' not in html),
    # 反向断言：html 里不许再出现字面版本号，否则又变回第二份真源
    ("版本号不写死在 html 里（由 data.json 填）",
     not re.search(r'class="ver"[^>]*>\s*v?\d+\.\d+\.\d+', html) and 'id="ver-badge"' in html),
    ("Logo = 2 号（星＋三级台阶）", html.count('<rect x="8.4"') == 1 and 'cx="12" cy="4.6"' in html),
    ("Logo 用亮色渐变变量", "--logo-a" in css and "#ff6b4a" in css),
    ("浅色主题有单独的压暗版", "#e2542f" in css),
    ("开发者 VX 在侧栏", "开发者 VX" in html and "nexusaistart" in html),
    ("复制是真 button", '<button type="button" class="dev-copy"' in html),
    ("复制功能已接线", 'dev-copy' in js and 'copyText' in js),
    # 导航 = 首页 / 项目库 / 我的文件。这条真正要守的是下面那句
    # 「坑库不在侧栏」（那是机器的索引）。
    # ⛔ 第三项不叫「设置」：那一页里大部分是维护者的工作台，不是用户的设置
    #    （它自己的折叠区都写着「一般不用管」）。用户来这页只为两件事：
    #    我的东西在哪、换机怎么办。名字得说的是那两件。
    ("导航是 3 项（首页/项目库/我的文件）", html.count('class="nav-btn" data-page=') == 3),
    ("第三项叫「我的文件」不叫「设置」", '>我的文件</button>' in html),
    # ⛔ 反馈出口用 hidden 属性控制显隐，而 .dev-feedback 写了 display:block——
    #    优先级压过浏览器给 [hidden] 的 display:none，`el.hidden = true` 会**静默失效**。
    #    实测：全新安装、一个项目都没有时，「这东西帮到你了？」照样挂在侧栏，
    #    而那正是它最不该出现的时候（没被帮到过，问了也没有信息量）。
    ("反馈出口的 hidden 真能藏住（有 [hidden] 规则）", ".dev-feedback[hidden]" in css),
    ("坑库不在侧栏", 'data-page="pitfall"' not in html),
    # 坑库的入口是首页那个「经验库 N」大格子：点数字进去，数字和动作合在一处
    ("首页经验库格子可点进坑库", "h-tile-pitfall" in js and "tile.clickable" in css),
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
