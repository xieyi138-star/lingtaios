# -*- coding: utf-8 -*-
"""把 exe 剖开，逐件核对灵魂真源与 skills 真源是否逐字节一致"""
import glob, hashlib, io, os, shutil, socket, subprocess, tempfile, time

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # tests 的上一级就是 brain-console
# release_pkg 是作者本机的发布目录，别人 clone 下来只有自己打出来的 dist——两个都认，
# 谁在就用谁，否则这行在别人机器上直接 FileNotFoundError。
# ⛔ 顺序是 dist 优先，不能反过来（这里曾经是 release_pkg 优先）：
#    ① run_all._exe() 就是 dist 优先，整套回归起的、验的都是 dist 那个 exe，
#       而这条却去剖 release_pkg 那个——**同一轮回归里测的是两个不同的二进制**；
#    ② release_pkg 装的是"上次打包那一版"，所以改任何一行源码，这条就红到
#       下次发版为止。常驻的红等于没有红——真出问题时没人分得出来。
#    ③ release_pkg 滞后本来就有 make_release.py 自己守（清空重建 + 逐字节回验），
#       而且它是直接拷 dist/lingtaios.exe 进包的，两者由构造保证同源，不存在漏网。
_CAND = [os.path.join(BC, d, "lingtaios.exe") for d in ("dist", "release_pkg")]
EXE = next((p for p in _CAND if os.path.isfile(p)), _CAND[0])
# 和 lingtaios.spec 同一个布局判定，必须同步改：
#   主源码  skills\brain-console\  → project-delivery 在**上一级**（兄弟目录）
#   发布仓  repo\                  → project-delivery 在**同级**（发布时摊平了）
# 写死 dirname(BC) 的话，从 clone 出来的仓里跑，20 件真源会全判「内容不同」——
# 实测过，比对的根本是另一个目录。
SKILLS = BC if os.path.isdir(os.path.join(BC, "project-delivery")) else os.path.dirname(BC)
DN = subprocess.DEVNULL

def sh(c):
    r = subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (r.stdout or b"").decode("mbcs", errors="replace")

def killport():
    for ln in sh('netstat -ano -p TCP').splitlines():
        p = ln.split()
        if len(p) >= 5 and p[0] == "TCP" and p[3] == "LISTENING" and p[1].endswith(":8765"):
            sh('taskkill /F /PID %s /T' % p[4])
    sh('taskkill /F /IM lingtaios.exe /T'); sh('taskkill /F /IM lt.exe /T')
    time.sleep(2)

def md5(p):
    try:
        return hashlib.md5(io.open(p, "rb").read()).hexdigest()
    except OSError:
        return None

# 灵魂清单：方法论真源 + 六器官种子 + 接入卡
SOUL = [
    ("常驻薄核（三条永不豁免·证据头·开窗五步）", "project-delivery/常驻薄核.md",      "project-delivery/常驻薄核.md"),
    ("项目交付法（四阶段+十二条纪律）",           "project-delivery/项目交付法.md",    "project-delivery/项目交付法.md"),
    ("核心大脑（六器官中枢）",                   "project-delivery/核心大脑.md",      "project-delivery/核心大脑.md"),
    ("道法术（执行/探索模式开关）",               "project-delivery/道法术.md",        "project-delivery/道法术.md"),
    # ⛔ 标签里不写条数：写死的「38 条」在坑库涨到 77 条之后还挂在屏幕上，
    #    每跑一次就对操作者撒一次谎。条数看界面/data.json，那是机器生成的。
    ("坑库（带失效判据）",                        "project-delivery/坑库.md",          "project-delivery/坑库.md"),
    ("装配图（唯一导航真源）",                   "project-delivery/装配图.md",        "project-delivery/装配图.md"),
    ("SKILL 路由器（四真源+开窗五步）",           "project-delivery/SKILL.md",         "project-delivery/SKILL.md"),
    ("派工/验收真源",                            "agent-worksheet/SKILL.md",          "agent-worksheet/SKILL.md"),
]
SEED = ["00_宪法.md", "01_法典.md", "03_在建.md", "04_待办池.md", "05_交接.md",
        "06_提案层.md", "关口清单.md", "规则台账.md", "状态源.示例.json", "状态生成器.py", "README.md"]

killport()
work = tempfile.mkdtemp(prefix="manifest_")
shutil.copy2(EXE, os.path.join(work, "lingtaios.exe"))
# ⛔ 两处写死过，都咬过人：
#   ① 路径写死 D:\Temp —— 换台机器 temp 不在那儿，这条就永远找不到 bundle
#   ② sorted() 是**按名字**排字符串，不是按时间。实测本机积压过 319 个 _MEI 目录
#      （taskkill 强杀不清理），名字最小的那个是几天前的旧版，于是拿旧包跟新真源比，
#      报「内容不同」——量具自己错了，却看起来像产品坏了（坑库 P1）。
_MEIGLOB = os.path.join(tempfile.gettempdir(), "_MEI*")
before = set(glob.glob(_MEIGLOB))
subprocess.Popen([os.path.join(work, "lingtaios.exe"), "--no-browser"], cwd=work, stdout=DN, stderr=DN)
up = False
for _ in range(150):
    s = socket.socket(); s.settimeout(0.4); up = s.connect_ex(("127.0.0.1", 8765)) == 0; s.close()
    if up: break
    time.sleep(0.4)
new = sorted(set(glob.glob(_MEIGLOB)) - before, key=os.path.getmtime, reverse=True)
bundle = new[0] if new else None
# 剖的是哪个 exe 必须打出来：dist 和 release_pkg 两个二进制长得一样，
# 结论却可能相反——不说清楚，红了要重新查一遍才知道量的是哪一个。
print("剖的 exe:", EXE)
print("exe 已展开到:", bundle, "（新出现 %d 个，取最新的）\n" % len(new))

ok = miss = diff = 0
print("=" * 88)
print("%-42s %-10s %s" % ("灵魂真源", "包内", "与你的真源比对"))
print("=" * 88)
for label, inbundle, insrc in SOUL:
    a = md5(os.path.join(bundle, inbundle)) if bundle else None
    b = md5(os.path.join(SKILLS, insrc))
    if a is None:
        v, mark = "缺失", "✗ 不在包里"; miss += 1
    elif a == b:
        v, mark = "在", "✓ 逐字节一致"; ok += 1
    else:
        v, mark = "在", "! 内容不同"; diff += 1
    print("%-42s %-10s %s" % (label, v, mark))

print("\n" + "-" * 88)
print("六器官种子（一键装系统的模板，装进每个项目的就是它们）")
print("-" * 88)
for f in SEED:
    a = md5(os.path.join(bundle, "project-delivery", "scaffold", f)) if bundle else None
    b = md5(os.path.join(SKILLS, "project-delivery", "scaffold", f))
    if a is None:
        print("  %-22s ✗ 不在包里" % f); miss += 1
    elif a == b:
        print("  %-22s ✓ 逐字节一致" % f); ok += 1
    else:
        print("  %-22s ! 内容不同" % f); diff += 1

a = md5(os.path.join(bundle, "AI开窗必读.md")) if bundle else None
# 接入卡在两种布局下都直接躺在 BC 下，不要再拼 brain-console 这一层：
# 拼了的话在发布仓布局里指向不存在的文件，md5() 返回 None，这一件被判成
# 「内容不同」——不是真的不同，是根本没读到。实测踩过。
b = md5(os.path.join(BC, "AI开窗必读.md"))
print("\n  %-22s %s" % ("AI开窗必读.md（接入卡）",
      "✓ 逐字节一致" if a and a == b else ("✗ 不在包里" if a is None else "! 内容不同")))
if a is None: miss += 1
elif a == b: ok += 1
else: diff += 1

print("\n" + "=" * 88)
print("一致 %d 件   内容不同 %d 件   缺失 %d 件" % (ok, diff, miss))
killport(); shutil.rmtree(work, ignore_errors=True)
