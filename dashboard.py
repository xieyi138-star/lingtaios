# -*- coding: utf-8 -*-
"""大脑驾驶舱 · 渲染引擎（stdlib + vendor/mdlite，零外部依赖）

用法:
    python -X utf8 dashboard.py              # 读真源 → site/data.json → 起服务 → 开浏览器
    python -X utf8 dashboard.py --no-browser # 起服务不开浏览器
    python -X utf8 dashboard.py --build-only # 只生成 data.json 不服务
    python -X utf8 dashboard.py --health     # 终端只跑真源健康检查
    python -X utf8 dashboard.py --selftest   # 破坏性自检

原则：只读真源，渲染即读，零副本。data.json 是生成物，人一个数字都不许手写。
"""
import argparse
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import mdlite  # noqa: E402

# PyInstaller onefile 适配：exe 所在目录 = 用户数据（roots.json/site/）；解包目录 = 只读资产（web/方法真源）
_FROZEN = getattr(sys, "frozen", False)
if _FROZEN and os.name == "nt":
    # 跟随控制台**实际**的输出代码页，不写死。
    # 中文 Windows 默认 936(GBK)，但 Win11 新终端 / VS Code / 跑过 chcp 65001 的窗口是 UTF-8。
    # 写死任何一边，都会在另一边把中文变成乱码——GBK 曾是写死的那一边。
    enc = "gbk"
    try:
        import codecs
        import ctypes
        cp = ctypes.windll.kernel32.GetConsoleOutputCP()  # 无控制台时返回 0
        if cp:
            codecs.lookup("cp%d" % cp)  # 不认识就抛 LookupError，留在 gbk
            enc = "cp%d" % cp           # cp936=GBK  cp65001=UTF-8
    except (OSError, AttributeError, LookupError):
        pass
    try:
        sys.stdout.reconfigure(encoding=enc, errors="replace")
        sys.stderr.reconfigure(encoding=enc, errors="replace")
    except (AttributeError, OSError):
        pass
if _FROZEN:
    HERE = os.path.dirname(os.path.abspath(sys.executable))
    BUNDLE = sys._MEIPASS  # noqa
    # ⛔ REPO 曾经 = BUNDLE，也就是 PyInstaller 每次启动新建的临时解压目录 _MEIxxxx。
    # 后果：坑库/装配图/方法论真源全指向临时目录——用户点「记坑」，接口返回 200、
    # 界面条数也涨了，**但进程一退出临时目录被清理，那条坑就没了**，而且悄无声息。
    # 实测：记一条 T6，rows 38→39，重启 exe 回到 38，主源码真源 md5 全程未变。
    # 这直接违反产品第一承诺「记忆归你 / 记忆是你的资产」，比装不上更坏——
    # 装不上是立刻可见的，这个是用着用着记忆没了。
    # 现在 REPO 指向 exe 旁边的持久目录，出厂模板首跑从 BUNDLE 落过来（见 _seed_repo）。
    # BUNDLE 只留给程序资源（web/），那些本来就该随包走、不该用户改。
    REPO = HERE
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
    BUNDLE = None
    # ⛔ 两种源码布局都要认（和 install.py / lingtaios.spec / tests 同一个判据）：
    #     主源码  skills\brain-console\dashboard.py → project-delivery 在**上一级**
    #     发布仓  repo\dashboard.py                 → 发布时摊平，在**同级**
    # 无条件 dirname(HERE) 的话，从公开仓 clone 下来按 README 跑
    # `python -X utf8 dashboard.py`，装配图/坑库/常驻薄核全部找不到。
    REPO = HERE if os.path.isdir(os.path.join(HERE, "project-delivery")) else os.path.dirname(HERE)
MAP = os.path.join(REPO, "project-delivery", "装配图.md")
PITFALL = os.path.join(REPO, "project-delivery", "坑库.md")
SITE = os.path.join(HERE, "site")
WEB = os.path.join(BUNDLE, "web") if BUNDLE else os.path.join(HERE, "web")


def _read_version():
    """版本号只有一份真源：release/VERSION（发布仓摊平后在根；打包后在 BUNDLE 根）。

    ⛔ 别在 index.html / README 里再各存一份。此前正是三处手写，靠 make_release
       的「版本号三处一致」检查兜着——而检查只拦得住**不一致**，拦不住
       **三处一起忘**，那时它照样绿着放行一个版本号全是旧值的包。
       「一份知识只能存一处，第二处必须由第一处生成。」
    """
    cands = ([os.path.join(BUNDLE, "VERSION")] if BUNDLE else []) + [
        os.path.join(HERE, "release", "VERSION"), os.path.join(HERE, "VERSION")]
    for p in cands:
        try:
            with io.open(p, encoding="utf-8-sig") as f:
                v = f.read().strip()
        except OSError:
            continue
        if v:
            return v
    return ""
ROOTS_FILE = os.path.join(HERE, "roots.json")
# --roots-file 是「演练/多机配置」用的。它以前只在启动时读一次，写回的却永远是
# ROOTS_FILE——演练一跑就污染真配置（实测把两个临时目录写进了本机 roots.json）。
# 演练不许碰真源：落点存成全局，读和写都认它。
ACTIVE_ROOTS_FILE = ROOTS_FILE
# 产物落点同样要跟着演练走。只挪配置不挪产物，演练照样会把 site/data.json 写花——
# 实测：一次向导演练把本机 22 个项目的快照冲成了 5 个临时目录。
# 「演练不许碰真源」要连产物一起算，否则堵一半等于没堵。
ACTIVE_SITE = SITE
METHOD_DOCS = [
    ("常驻薄核", os.path.join(REPO, "project-delivery", "常驻薄核.md")),
    ("道法术", os.path.join(REPO, "project-delivery", "道法术.md")),
    ("项目交付法", os.path.join(REPO, "project-delivery", "项目交付法.md")),
    ("核心大脑", os.path.join(REPO, "project-delivery", "核心大脑.md")),
]
PITFALL_SECTIONS = ["判定侧", "协作与派工", "状态与文档", "运行时与系统", "工具坑"]
ORGANS = ["00_宪法.md", "01_法典.md", "02_状态.md", "03_在建.md", "04_待办池.md",
          "05_交接.md", "06_提案层.md", "关口清单.md", "规则台账.md"]
ALIASES = {"SKILLS", "NEXUS", "D", "HOME"}


def load_roots(path=None):
    p = path or ACTIVE_ROOTS_FILE
    if not os.path.isfile(p):
        print("[XX] 缺 roots.json（%s）—— 先跑：python -X utf8 install.py" % p)
        sys.exit(2)
    with io.open(p, encoding="utf-8") as f:
        d = json.load(f)
    r = dict(d.get("roots", {}))
    r["machine_id"] = d.get("machine_id", "")
    # 老 roots.json 没有 setup_done → 当作已完成，不给现有用户弹向导
    r["_setup_done"] = bool(d.get("setup_done", True))
    # 工作区 = 装项目的目录，它底下一层就是项目。比逐个登记项目强在「动态」：
    # 以后在工作区里新建项目会自动出现，不用回来改配置。
    r["_workspaces"] = list(d.get("workspaces", []) or [])
    r["_projects"] = list(d.get("projects", []) or [])      # 工作区之外单独加的
    r["_excluded"] = [os.path.normcase(x) for x in (d.get("excluded", []) or [])]
    return r


# ── 向导 API（v0.2 · 傻瓜式：点按钮，不背规则）─────────────────────

PROJECT_NAME_RE = re.compile(r"^[\w一-龥\- ]+$")
SCAFFOLD_FILES = ["00_宪法.md", "01_法典.md", "03_在建.md", "04_待办池.md",
                  "05_交接.md", "06_提案层.md", "关口清单.md", "规则台账.md", "状态生成器.py"]


def api_templates():
    """把**方法**交给一个还没绑定项目的 AI。开工用的不是这个，见 api_project_detail 的 resume。

    ⛔ 这段以前混进了 `读本项目 brain\\01_法典.md`、`更新进 brain\\05_交接.md`。
       「本项目」是哪个？没说。`brain\\...` 是没有根的相对路径——粘给 AI，
       它只能反问「哪个项目」或者在当前目录瞎猜。而它当时挂在首页**最显眼的
       主按钮**上，叫「复制开窗三句话」（实际四行）。
       开工必须绑定到一个具体项目，那件事由项目详情页的「继续做」指令负责，
       它给的是完整绝对路径。这里只留**不需要项目也成立**的两步。
    """
    card = os.path.join(HERE, "AI开窗必读.md")
    open_text = (
        "1. 先读 %s（AI开窗必读，照做开窗五步）\n"
        "2. 每段回复第一行打证据头：先用工具读出真实状态再说，没查过就标「无证据」；\n"
        "   不可逆动作先出施工图等我拍板\n"
        "（要接着做某个具体项目：打开灵台 → 点那个项目 → 「复制『继续做』指令」，"
        "那份带着这台机器上的真实路径）"
    ) % card
    close_text = (
        "按收窗四步收：①销账（回状态源标死已完成项）②教训进坑库/法典（不记流水账）"
        "③C 类过程标到期 ④更新 brain\\05_交接.md\n"
        "收完%s 并报告告警" % _regen_cmd()
    )
    return {"ok": True, "open": open_text, "close": close_text,
            "paths": {"card": card, "map": MAP}}


def _sandbox_marker(roots):
    nexus = roots.get("NEXUS") or ""
    return os.path.normcase(os.path.join(nexus, "sandbox")) + os.sep


def _reject_sandbox(target, roots):
    """红线：sandbox 只读区。返回 (status, payload) 或 None。"""
    if os.path.normcase(target).startswith(_sandbox_marker(roots)):
        return 403, {"ok": False, "error": "sandbox 是只读区（创始人指令 2026-08-15），换一个落点"}
    return None


def _install_organs_files(target, name, goals=None, redlines=None, retro=False):
    """复制 scaffold 六器官进 target\\brain\\ 并做最小填充。只写新目录，不碰项目原文件。"""
    brain = os.path.join(target, "brain")
    os.makedirs(brain)
    scaffold = os.path.join(REPO, "project-delivery", "scaffold")
    for f in SCAFFOLD_FILES:
        shutil.copyfile(os.path.join(scaffold, f), brain + os.sep + f)

    # 填 00 宪法：项目名 + 果五栏 + 红线
    goals = [g for g in (goals or []) if (g.get("name") or "").strip()][:5]
    if goals:
        rows = "\n".join(
            "| %s | %s | %s | %s | %s |" % (
                g.get("name", "").replace("|", "/"),
                g.get("def", "").replace("|", "/"),
                g.get("who", "创始人"),
                g.get("when", "每天"),
                g.get("line", "").replace("|", "/"),
            )
            for g in goals
        )
    else:
        rows = "| | | | | |"
    goal_block = "| 指标 | 定义 | 谁来测 | 何时测 | 达标线 |\n|---|---|---|---|---|\n" + rows
    reds = [r.strip() for r in (redlines or []) if r.strip()]
    if reds:
        red_block = "\n".join("🔴 " + r for r in reds)
    else:
        red_block = ("🔴 （待填：本项目绝不做的事）" if not retro else
                     "🔴 历史文件先读后改：动任何原文件前，先读相关交接/施工图，改必留痕\n🔴 （待填：本项目绝不做的事）")

    const_path = os.path.join(brain, "00_宪法.md")
    with io.open(const_path, encoding="utf-8") as f:
        const = f.read()
    const = const.replace("# 宪法 · <项目名>", "# 宪法 · " + name)
    const = const.replace(
        "| 指标 | 定义 | 谁来测 | 何时测 | 达标线 |\n|---|---|---|---|---|\n| | | | | |",
        goal_block)
    const = const.replace("🔴 \n🔴 ", red_block + "\n")
    with io.open(const_path, "w", encoding="utf-8") as f:
        f.write(const)

    # 填 01 法典
    codex_path = os.path.join(brain, "01_法典.md")
    with io.open(codex_path, encoding="utf-8") as f:
        codex = f.read()
    codex = codex.replace("# 法典 · <项目名>", "# 法典 · " + name)
    codex = codex.replace(
        "🔴 <绝不做的事 1>\n🔴 <绝不做的事 2>", "🔴 见 00_宪法.md 三 · 红线（不复制，一处真源）")
    codex = codex.replace("- **文件地图**：<核心文件在哪>", "- **文件地图**：项目根 + `brain/` 六器官（真源导航见装配图）")
    codex = codex.replace("- **当前阶段目标**：<这一阶段要拿到什么>", "- **当前阶段目标**：见 `03_在建.md` 注-001")
    codex = codex.replace("- **真源指定**：道=<...> 法=<...> 术=<...> 关键数字=<...>",
                          "- **真源指定**：道=项目交付法 法=核心大脑六器官 术=坑库（`~/.claude/skills/project-delivery/`，开工前查装配图）")
    with io.open(codex_path, "w", encoding="utf-8") as f:
        f.write(codex)

    # 填 03 在建
    plan_path = os.path.join(brain, "03_在建.md")
    with io.open(plan_path, encoding="utf-8") as f:
        plan = f.read()
    plan = plan.replace("### 注-001 · <一句话名字>",
                        "### 注-001 · %s" % ("续做（一键装系统）" if retro else "立项：" + name))
    plan = plan.replace("| **服务哪个终极指标** | <说不出就不开工> |", "| **服务哪个终极指标** | 见 `00_宪法.md` 一 · 终极之果 |")
    with io.open(plan_path, "w", encoding="utf-8") as f:
        f.write(plan)

    # 填 05 交接（续装项目：进度接历史 HANDOFF/施工图，不复制内容）
    hand_p = os.path.join(brain, "05_交接.md")
    with io.open(hand_p, encoding="utf-8") as f:
        hand = f.read()
    hand = hand.replace("**最近一次生成**：<日期>　**有无告警**：<有/无>",
                        "**最近一次生成**：%s　**有无告警**：看 02_状态.md 顶部" % time.strftime("%Y-%m-%d"))
    if retro:
        hand = hand.replace("见 `03_在建.md`。一句话：<...>",
                            "见 `03_在建.md`。一句话：续做历史项目——原进度与结论在项目根的交接/施工图文档里（驾驶舱详情页可见），本脑从「下一步」接手。")
    else:
        hand = hand.replace("见 `03_在建.md`。一句话：<...>",
                            "见 `03_在建.md`。一句话：新项目立项，从果五栏开工。")
    with io.open(hand_p, "w", encoding="utf-8") as f:
        f.write(hand)

    # 通用 状态源.json
    state_src = {
        "_说明": "基础探针。真源探针后期按项目精调（加 expect 对账闸）。",
        "project": name,
        "root": "..",
        "probes": [
            {"name": "器官·六卡文件数", "type": "file_count", "glob": "brain/0[013456]_*.md"},
            {"name": "待办·条数", "type": "regex_count", "glob": "brain/04_待办池.md", "pattern": "^\\| [0-9]+ \\|"},
        ],
        "health": [],
        "outcomes": [],
    }
    with io.open(os.path.join(brain, "状态源.json"), "w", encoding="utf-8") as f:
        json.dump(state_src, f, ensure_ascii=False, indent=2)
    return brain


def _alias_row(target, roots):
    for alias, root in (("NEXUS", roots.get("NEXUS")), ("D", roots.get("D"))):
        if root:
            rn = os.path.normcase(os.path.abspath(root)).rstrip("\\/")
            if os.path.normcase(target).startswith(rn + os.sep):
                return "{%s}/%s" % (alias, os.path.relpath(target, root).replace("\\", "/"))
    return target


def api_create_project(data):
    name = (data.get("name") or "").strip()
    if not PROJECT_NAME_RE.match(name) or name in (".", ".."):
        return 400, {"ok": False, "error": "项目名含非法字符（限中英文/数字/-/空格）"}
    roots = load_roots()
    # ⛔ 默认值曾经是 "nexus"——把作者机器上的 C:\nexus_local 当成了所有人的默认落点。
    # 界面会按实况生成选项所以没暴露，但直接调 API 的（比如 AI 代跑）一撞一个准。
    # 现在不给默认：没指定就报错，并把这台机器上**实际可用**的选项列出来。
    choice = (data.get("root_choice") or "").strip().lower()
    avail = [a.lower() for a in ("NEXUS", "D") if roots.get(a)]
    if not choice:
        return 400, {"ok": False, "error":
                     "没指定落点 root_choice。这台机器可选：%s；或用 custom 并给 custom_path"
                     % (", ".join(avail) if avail else "（本机没有已配置的业务根，只能用 custom）")}
    if choice == "nexus":
        base = roots.get("NEXUS")
    elif choice == "d":
        base = roots.get("D")
    elif choice == "custom":
        base = (data.get("custom_path") or "").strip()
        if not base or not os.path.isdir(base):
            return 400, {"ok": False, "error": "自定义路径不存在：%s" % (base or "（空）")}
    else:
        return 400, {"ok": False, "error": "root_choice 不合法：%s（可选 nexus / d / custom）" % choice}
    if not base:
        # 别再叫人去跑 install.py——下载 exe 用的人根本没有源码，跑不了。
        return 400, {"ok": False, "error":
                     "这台机器上没配 {%s} 这个根。换个落点：用 custom 指定一个文件夹"
                     "（新项目页「选一个文件夹…」），或到设置里把根配上。"
                     % choice.upper()}
    target = os.path.abspath(os.path.join(base, name))
    rej = _reject_sandbox(target, roots)
    if rej:
        return rej
    if os.path.exists(target):
        return 400, {"ok": False, "error": "目标已存在：%s" % target}
    try:
        _install_organs_files(target, name, data.get("goals"), data.get("redlines"))
    except OSError as e:
        return 500, {"ok": False, "error": str(e)}

    # 跑生成器，02_状态 出生
    gen = _run_generator(os.path.join(target, "brain"))
    # 登记进装配图 L6（先改图再动文件——本接口把两者合成一个动作）
    map_row = None
    for alias, root in (("NEXUS", roots.get("NEXUS")), ("D", roots.get("D"))):
        if root:
            rn = os.path.normcase(os.path.abspath(root)).rstrip("\\/")
            if os.path.normcase(target).startswith(rn + os.sep):
                map_row = "{%s}/%s" % (alias, os.path.relpath(target, root).replace("\\", "/"))
                break
    if map_row is None:
        map_row = target  # 自定义路径：绝对路径登记（本机专属）
    _register_in_map("### L6", "| `%s` | 项目层 | 向导创建 %s |" % (map_row, time.strftime("%Y-%m-%d")))
    # ⛔ 登记进装配图**还不够**：discover_projects 只认 L6 里 {D}/ 开头的行，
    # 自定义落点登记的是绝对路径，它不认——于是项目建出来了、六器官也落盘了，
    # 项目库里却是空的。新用户 100% 撞这个：他没有 NEXUS/D 根，只能选自定义落点。
    # 所以创建完一律显式登记进项目库，跟「＋ 添加项目」走同一条路。
    try:
        with _CONF_LOCK:
            _project_add_locked(target, False)   # 它内部会 build，下面就不用再 build
    except Exception:
        try:
            build(load_roots(), ACTIVE_SITE)
        except Exception:
            pass
    return 200, {"ok": True, "path": target, "organs": SCAFFOLD_FILES,
                 "generator": gen}


def api_install_organs(data):
    """一键给历史项目装系统：只新增 brain\\，绝不触碰项目原文件。允许 sandbox 项目。"""
    path = (data.get("path") or "").strip()
    if not path or not os.path.isdir(path):
        return 400, {"ok": False, "error": "项目路径不存在"}
    if os.path.isdir(os.path.join(path, "brain")):
        return 400, {"ok": False, "error": "已装系统（brain\\ 已存在）"}
    roots = load_roots()
    target = os.path.abspath(path)
    try:
        brain = _install_organs_files(target, os.path.basename(path), retro=True)
    except OSError as e:
        return 500, {"ok": False, "error": str(e)}
    gen = _run_generator(brain)
    _register_in_map("### L6", "| `%s` | 项目层 | 一键装系统 %s |" % (
        _alias_row(target, roots), time.strftime("%Y-%m-%d")))
    try:
        build(load_roots(), ACTIVE_SITE)
    except Exception:
        pass
    return 200, {"ok": True, "path": target, "organs": SCAFFOLD_FILES,
                 "generator": gen}


def _pit_section_of(code):
    return {"P": "判定侧", "W": "协作与派工", "S": "状态与文档", "R": "运行时与系统", "T": "工具坑"}.get(code[0])


def api_add_pitfall(data):
    """进坑向导：防法+失效判据缺一不放行（涨有门槛）。追加进坑库.md 对应小节。"""
    section = (data.get("section") or "").strip()
    pit = (data.get("pit") or "").strip()
    fix = (data.get("fix") or "").strip()
    source = (data.get("source") or "").strip()
    invalid_when = (data.get("invalid_when") or "").strip()
    if section not in PITFALL_SECTIONS:
        return 400, {"ok": False, "error": "分区不合法：%s" % section}
    if not pit or not fix or not invalid_when:
        return 400, {"ok": False, "error": "「坑」「防法」「失效判据」三项必填——缺一不许入库"}
    with io.open(PITFALL, encoding="utf-8") as f:
        text = f.read()
    rows = mdlite.table_rows(text, section)
    prefix = {"判定侧": "P", "协作与派工": "W", "状态与文档": "S", "运行时与系统": "R", "工具坑": "T"}[section]
    nums = [int(r["编号"][1:]) for r in rows if re.fullmatch(r"%s\d+" % prefix, r.get("编号", ""))]
    code = "%s%d" % (prefix, max(nums) + 1 if nums else 1)
    # 末尾的「贡献者」留空 = 本库主人自己记的。有值 = 社区贡献并被采纳的。
    # 给贡献者的回报是**署名**不是钱：实证表明金钱激励会挤出内在动机（小额挤得最狠），
    # 而地位/声誉动机反过来会增强它——署名成本为零，也不会引来刷量的人。
    #
    # ⛔ 列数要跟着**这个文件当前的表头**走，不能写死。
    #    老用户的坑库是 7 列（没有「贡献者」），升级后如果按 8 列写，
    #    新行会比表格宽一格，整张表在解析和渲染上都会错位。
    #    这类「新版本写坏老数据」的兼容问题，装了才发现就晚了。
    has_contrib = "贡献者" in (rows[0].keys() if rows else {}) or "| 贡献者 |" in text
    new_row = "| %s | %s | %s | %s | 1 | %s | %s |%s" % (
        code, pit.replace("|", "/"), fix.replace("|", "/"), source.replace("|", "/"),
        invalid_when.replace("|", "/"), time.strftime("%Y-%m-%d"),
        "  |" if has_contrib else "")
    lines = text.split("\n")
    sec_idx = next(i for i, ln in enumerate(lines) if ln.startswith("## %s" % section))
    nxt = next((i for i in range(sec_idx + 1, len(lines))
                if lines[i].startswith("## ")), len(lines))
    insert_at = max(i for i in range(sec_idx, nxt) if lines[i].startswith("| "))
    lines.insert(insert_at + 1, new_row)
    with io.open(PITFALL, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    try:
        build(load_roots(), ACTIVE_SITE)
    except Exception:
        pass
    return 200, {"ok": True, "code": code}


def api_audit_delete(data):
    """汰有机制：按编号删坑库行 / 按 # 删待办池行。只删精确匹配行，git 回滚点保护。"""
    kind = data.get("kind")
    ids = data.get("ids") or []
    if not ids:
        return 400, {"ok": False, "error": "没选任何条目"}
    if kind == "pitfall":
        with io.open(PITFALL, encoding="utf-8") as f:
            text = f.read()
        lines = text.split("\n")
        keep = [ln for ln in lines
                if not any(re.match(r"^\| %s \|" % re.escape(i), ln) for i in ids)]
        removed = len(lines) - len(keep)
        if not removed:
            return 400, {"ok": False, "error": "没有匹配的行被删（编号不对？）"}
        with io.open(PITFALL, "w", encoding="utf-8") as f:
            f.write("\n".join(keep))
        try:
            build(load_roots(), ACTIVE_SITE)
        except Exception:
            pass
        return 200, {"ok": True, "removed": removed}
    if kind == "todo":
        path = (data.get("path") or "").strip()
        todo_p = os.path.join(path, "brain", "04_待办池.md")
        if not os.path.isfile(todo_p):
            return 400, {"ok": False, "error": "待办池不存在：%s" % todo_p}
        with io.open(todo_p, encoding="utf-8") as f:
            text = f.read()
        lines = text.split("\n")
        keep = [ln for ln in lines
                if not any(re.match(r"^\| %s \|" % re.escape(i), ln) for i in ids)]
        removed = len(lines) - len(keep)
        with io.open(todo_p, "w", encoding="utf-8") as f:
            f.write("\n".join(keep))
        try:
            build(load_roots(), ACTIVE_SITE)
        except Exception:
            pass
        return 200, {"ok": True, "removed": removed}
    return 400, {"ok": False, "error": "kind 不合法"}


# 失效判据的强度分档用词表。
# 判据的唯一作用是「它成立时这条坑不可能再发生」——成立了就整行删。所以判据必须是
# 一个能查真假的**结构性状态**。三种写法会让它形同虚设：
#   循环（判据只是把防法换个说法，照它判永远判不出「已消除」）
#   空话（靠人自觉：注意/记得/应该）
#   不可判（没说谁来验、拿什么验）
# ⛔ 这只是文本特征，判不了「判据对不对」——只能挑出可疑的给人看，别当结论。
_CRIT_HARD = ("回归", "用例", "自检", "静态检查", "断言", "退出码", "报错", "拒绝", "抛错",
              "工具", "校验", "字段", "元数据", "指纹", "版本号", "生成", "同源", "搜不到",
              "创建不出来", "执行不了", "不允许", "不放行", "不许", "会被", "自动",
              # 这几个是自检喂坏样本时补上的：「强制」「不存在」「必填」都是可查证的
              # 结构性状态，漏了会把明确的强判据错判成中。
              "强制", "不存在", "不再有", "必填", "拦下", "挡住")
_CRIT_SOFT = ("注意", "记得", "应该", "尽量", "小心", "养成", "习惯", "牢记", "意识")


def _crit_overlap(a, b):
    """两段中文的字符重合率——判据和防法太像，就是把防法抄了一遍（循环）。"""
    sa, sb = set(a or ""), set(b or "")
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / float(min(len(sa), len(sb)))


def grade_criterion(crit, fix):
    """给一条失效判据打强度：强 / 中 / 弱 + 可疑理由。"""
    crit = (crit or "").strip()
    if not crit or crit == "待补":
        return "缺", "还没写"
    if any(w in crit for w in _CRIT_SOFT):
        return "弱", "靠人自觉，没有东西执行它"
    hard = sum(1 for w in _CRIT_HARD if w in crit)
    ov = _crit_overlap(crit, fix)
    # ⛔ 光看「和防法像不像」会大面积误伤：中文常用字重合度天然就高，
    #    实测把 5 条带「强制 / 不再有」的结构性判据全判成了循环。
    #    真正的循环是**既抄了防法、又一个结构性词都没有**——那才是把「人照做」
    #    当成了「坑已消除」。假阳性会让这条提示变噪音，人就不看了。
    if ov >= 0.72 and hard == 0:
        return "弱", "只是把防法换个说法（雷同 %d%%），照它判永远判不出「已消除」" % int(ov * 100)
    if hard >= 2 and ov < 0.6:
        return "强", "说清了谁来验、拿什么验"
    return "中", "是结构性状态，但没写明谁来执行"


def evolution_data(projects, pit_rows, health):
    """进化审计六清单：待补判据 / **判据强度** / 候选删除 / C类到期 / 交接过期 / 断头双份。"""
    import datetime
    today = time.strftime("%Y-%m-%d")
    missing_invalid = [r for r in pit_rows if (r.get("失效判据") or "").strip() in ("", "待补")]
    candidates = []
    for r in pit_rows:
        d = (r.get("入库") or "").strip()
        trig = (r.get("触发") or "").strip()
        try:
            dt = datetime.datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            continue
        if (datetime.datetime.now() - dt).days > 90 and trig in ("", "0", "1", "—", "-"):
            candidates.append(r)
    expired_todos = []
    for p in projects:
        todo_p = os.path.join(p["path"], "brain", "04_待办池.md")
        if not os.path.isfile(todo_p):
            continue
        text = _read_md(todo_p) or ""
        for ln in text.split("\n"):
            m = re.search(r"C·(\d{4}-\d{2}-\d{2})", ln)
            if m and m.group(1) < today and ln.strip().startswith("|"):
                expired_todos.append({"project": p["name"], "path": p["path"],
                                      "line": ln.strip()[:140]})
    stale_handoffs = []
    for p in projects:
        hp = os.path.join(p["path"], "brain", "05_交接.md")
        if os.path.isfile(hp):
            try:
                age = (time.time() - os.path.getmtime(hp)) / 86400.0
            except OSError:
                continue
            if age > 7:
                stale_handoffs.append({"project": p["name"], "path": p["path"], "days": int(age)})
    # 本周新增坑（"越用越强"的可见证据）
    import datetime as _dt
    week_ago = (_dt.datetime.now() - _dt.timedelta(days=7)).strftime("%Y-%m-%d")
    # ⛔ 只按日期算是错的：出厂那几十条带着**作者**的入库日期，用户刚装完什么都没干，
    #    首页就写「本周 +77」，把作者的批量并库算成了他的战果。
    #    一个满口「先实证再开口」的产品，首屏摆一个编出来的数字，比少一个数字贵得多。
    #    打包态能精确区分：BUNDLE 里那份坑库就是出厂快照，编号不在里面的才是用户自己记的。
    factory = _factory_pit_codes()
    new_this_week = sum(
        1 for r in pit_rows
        if (r.get("入库") or "") >= week_ago
        and (not factory or (r.get("编号") or "") not in factory))
    # 判据强度：让「这条判据可不可信」在界面上随手可见，而不是等到要删时才发现它是空话
    graded, grade_stats = [], {"强": 0, "中": 0, "弱": 0, "缺": 0}
    for r in pit_rows:
        g, why = grade_criterion(r.get("失效判据"), r.get("防法（照做即可）"))
        grade_stats[g] = grade_stats.get(g, 0) + 1
        if g in ("弱", "缺"):
            graded.append({"编号": r.get("编号", ""), "一句话坑": r.get("一句话坑", ""),
                           "失效判据": (r.get("失效判据") or "").strip(),
                           "grade": g, "why": why})
    return {
        "missing_invalid": missing_invalid,
        "weak_criteria": graded,
        "grade_stats": grade_stats,
        "candidates": candidates,
        "expired_todos": expired_todos,
        "stale_handoffs": stale_handoffs,
        "broken": health["missing"],
        "identical_pairs": health["identical_pairs"],
        "new_this_week": new_this_week,
        "total_pitfalls": len(pit_rows),
        # 升级传播：新版带来的方法论更新里，哪些没能自动生效、为什么（见 _seed_repo）
        "seed_kept": (_seed_state().get("kept") or []),
        "seed_pending": (_seed_state().get("pending") or []),
    }


_FACTORY_PIT_CODES = None


def _factory_pit_codes():
    """出厂就带的坑编号集合；源码态返回空集（那份库本身就是出厂，无从区分）。

    只读 BUNDLE（PyInstaller 每次启动新建的解压目录）里那份，它是**打包那一刻**的
    快照，用户后来记的坑只在 exe 旁边的持久目录里，不会混进来。
    """
    global _FACTORY_PIT_CODES
    if _FACTORY_PIT_CODES is None:
        codes = set()
        if BUNDLE:
            p = os.path.join(BUNDLE, "project-delivery", "坑库.md")
            try:
                with io.open(p, encoding="utf-8") as f:
                    codes = set(re.findall(r"^\|\s*([PWSRT]\d+)\s*\|", f.read(), re.M))
            except OSError:
                codes = set()
        _FACTORY_PIT_CODES = codes
    return _FACTORY_PIT_CODES


def _map_write_target():
    """演练态往哪写装配图。

    ⛔ 「演练不许碰真源」这条上一轮堵了配置（roots.json）和产物（site/data.json），
       漏了第三样：**装配图**。api_install_organs 会 _register_in_map 追加一行 L6，
       而那一行永远写真 MAP——实测新加的回归脚本用 --roots-file 跑了 4 次，
       就往本机装配图塞进 4 条指向临时目录的死登记（跑完目录删了，登记留着，
       健康检查从此 total=63/absent=4）。堵一半等于没堵，这次连它一起算。
    """
    if os.path.normcase(ACTIVE_ROOTS_FILE) == os.path.normcase(ROOTS_FILE):
        return MAP
    return os.path.join(os.path.dirname(ACTIVE_ROOTS_FILE), "装配图.演练.md")


def _register_in_map(section_marker, new_row):
    """在装配图指定小节末表格追加一行（真源登记，先改图）。

    演练态写到演练目录的副本，绝不碰真装配图——见 _map_write_target。
    """
    target = _map_write_target()
    # 演练副本第一次写之前不存在，就从真图起个头：演练看到的导航内容跟真的一样，
    # 但从此以后所有写入都落在副本上。
    src = target if os.path.isfile(target) else MAP
    with io.open(src, encoding="utf-8") as f:
        lines = f.read().split("\n")
    sec_idx = next((i for i, ln in enumerate(lines) if ln.startswith(section_marker)), None)
    if sec_idx is None:
        return
    nxt = next((i for i in range(sec_idx + 1, len(lines))
                if lines[i].startswith("### ") or lines[i].startswith("## ")), len(lines))
    insert_at = max(i for i in range(sec_idx, nxt) if lines[i].startswith("|"))
    if new_row not in lines:
        lines.insert(insert_at + 1, new_row)
        with io.open(target, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


# ── 首跑向导：让用户指自己的目录，而不是猜 ─────────────────────
# 扫描代价实测（本机，含下面这份排除清单）：C:\ 深度3 = 0.1s/385 目录，
# 深度4 = 0.4s/1431；D:\ 深度3 = 0.2s/737。深度 4 候选涨到 138 噪声明显变多，
# 所以默认深度 3——够扫到 sandbox 下面一层的项目，又不至于把整盘的 README 都端上来。
SCAN_SKIP = {
    "windows", "program files", "program files (x86)", "programdata", "recovery",
    "$recycle.bin", "system volume information", "appdata", "node_modules",
    "__pycache__", "temp", "tmp", "perflogs", "$windows.~ws", "onedrivetemp",
    "site-packages", "venv", ".venv", "dist", "build", "vendor", "web",
    "brain",  # 六器官目录，属于它的父项目，不是独立项目（检器官靠 listdir，不用遍历进去）
    "users", "documents and settings", "public", "default",  # 系统目录，不是谁的工作区
}
ORGAN_HINT = ("00_宪法.md", "01_法典.md", "02_状态.md", "05_交接.md")
# 路径里出现这些段 = 软件把插件/扩展装在这儿，里面是别人的东西不是你的项目
SOFTWARE_SEG = {"custom_nodes", "extensions", "plugins", "addons", "bower_components", "packages"}

ENGINEER_FILES = ("package.json", "pyproject.toml", "requirements.txt", "setup.py",
                  "cargo.toml", "go.mod", "pom.xml", "build.gradle", "composer.json",
                  "gemfile", "makefile", "docker-compose.yml", "dockerfile", "tsconfig.json")


def api_setup_save(data):
    """向导落盘。⛔ 只写 roots.json，不碰任何真源。"""
    workspaces = [str(p) for p in (data.get("workspaces") or []) if str(p).strip()]
    workspaces = sorted(set(p for p in workspaces if os.path.isdir(p)))
    excluded = sorted(set(str(p) for p in (data.get("excluded") or []) if str(p).strip()))
    projects = [str(p) for p in (data.get("projects") or []) if str(p).strip()]
    projects = [p for p in projects if os.path.isdir(p)]
    # 去重兜底：单独加的若已被某个「整个文件夹」罩住，就不必再单列一遍。
    # 前端也做了这层，但配置是要落盘的东西——前端漏一次就脏一次，这里必须再挡一道。
    ws_pref = [os.path.normcase(w).rstrip("\\/") + os.sep for w in workspaces]
    projects = [p for p in projects
                if not any(os.path.normcase(p).startswith(w) for w in ws_pref)
                and not any(os.path.normcase(p).rstrip("\\/") + os.sep == w for w in ws_pref)]
    # 前端不传某个根 → 沿用现有值（多半是首跑自动探测出来的），别把它抹成 null：
    # 否则在本机跑一遍向导，{NEXUS} 就没了，几十条真源集体变「无根」。
    cur = {}
    if os.path.isfile(ACTIVE_ROOTS_FILE):
        try:
            with io.open(ACTIVE_ROOTS_FILE, encoding="utf-8") as f:
                cur = (json.load(f) or {}).get("roots") or {}
        except (OSError, ValueError):
            cur = {}
    incoming = data.get("roots") or {}
    roots = {}
    for alias in ("NEXUS", "D", "HOME"):
        v = incoming.get(alias, cur.get(alias))
        v = str(v).strip() if v else ""
        roots[alias] = v if (v and os.path.isdir(v)) else None
    if not roots.get("HOME"):
        roots["HOME"] = os.path.expanduser("~")
    payload = {
        "machine_id": os.environ.get("COMPUTERNAME") or "unknown",
        "roots": roots,
        "workspaces": workspaces,
        "projects": sorted(set(projects)),
        "excluded": excluded,
        "setup_done": True,
    }
    try:
        with _CONF_LOCK:
            with io.open(ACTIVE_ROOTS_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError as e:
        return 500, {"ok": False, "error": "写 roots.json 失败：%s" % e}
    data2 = build(load_roots(), ACTIVE_SITE)  # 立即重算，用户点完就能看到自己的项目
    return 200, {"ok": True, "roots": roots, "workspaces": workspaces,
                 "projects": payload["projects"], "excluded": excluded,
                 "found": len(data2.get("projects", []))}


DRIVE_KIND = {2: "removable", 3: "fixed", 4: "remote", 5: "cdrom", 6: "ramdisk"}


def list_drives():
    """列盘符。⛔ 全程零 IO：用位图 + GetDriveType，不碰 os.path.isdir——
    对一个断开的网络映射盘，isdir 会卡几十秒，把整个向导僵住。
    外接硬盘/U 盘/网络盘照样列出来（客户的项目可能就在上面），
    但默认不勾：移动盘可能是几 T 的备份盘，网络盘慢且随时会断，让用户自己决定。"""
    out = []
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
    except (ImportError, AttributeError, OSError):
        # 非 Windows 或拿不到 API：退回老办法，至少别把功能丢了
        for c in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            p = "%s:\\" % c
            if os.path.isdir(p):
                out.append({"path": p, "kind": "fixed", "label": "", "default": True})
        return out
    bitmap = k32.GetLogicalDrives()
    for i in range(26):
        if not (bitmap & (1 << i)):
            continue
        path = "%s:\\" % chr(ord("A") + i)
        kind = DRIVE_KIND.get(k32.GetDriveTypeW(ctypes.c_wchar_p(path)), "unknown")
        if kind in ("cdrom", "ramdisk", "unknown"):
            continue  # 光驱/内存盘上不会有项目
        label = ""
        if kind != "remote":  # 网络盘读卷标同样可能卡，跳过
            buf = ctypes.create_unicode_buffer(261)
            try:
                if k32.GetVolumeInformationW(ctypes.c_wchar_p(path), buf, 260,
                                             None, None, None, None, 0):
                    label = buf.value or ""
            except (OSError, ValueError):
                label = ""
        out.append({"path": path, "kind": kind, "label": label,
                    "default": kind == "fixed"})
    return out


# 配置是「读 → 改 → 写」三步，多个请求同时来就会互相覆盖。
# 实测：3 个并发「移出项目库」只生效 2 个，另一个被后写的盖掉了。
_CONF_LOCK = threading.RLock()


def _clean_path(v):
    """路径入口统一净化。⛔ 别信任何外部传进来的类型——
    实测 path 传个数字就 12345.strip() → AttributeError 崩在 handler 里。"""
    if v is None:
        return ""
    try:
        return str(v).strip().strip('"')
    except Exception:
        return ""


def _reject_bad_project_path(path):
    """挡住不该当项目的路径。⛔ 不是替用户做主，是挡明显的误操作：
    实测把 C:\\Windows\\System32、\\\\?\\C:\\、..\\.. 传进来都会被当成项目收下，
    列表里冒出 System32、空名字。整盘或系统目录被登记成项目，
    后果是驾驶舱去扫几十万个文件。"""
    try:
        p = os.path.normcase(os.path.abspath(str(path))).rstrip("\\/")
    except (TypeError, ValueError, OSError):
        return "路径不合法"
    if not p or len(p) <= 2 or p.endswith(":"):
        return "整个盘符不能当项目，请选具体的项目文件夹"
    for env in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
        sd = os.environ.get(env)
        if not sd:
            continue
        sd = os.path.normcase(os.path.abspath(sd)).rstrip("\\/")
        if p == sd or p.startswith(sd + os.sep):
            return "这是系统目录，不能当项目"
    return None


def _load_conf():
    if os.path.isfile(ACTIVE_ROOTS_FILE):
        try:
            with io.open(ACTIVE_ROOTS_FILE, encoding="utf-8") as f:
                return json.load(f) or {}
        except (OSError, ValueError):
            return {}
    return {}


def _save_conf(conf):
    with io.open(ACTIVE_ROOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(conf, f, ensure_ascii=False, indent=2)


def api_project_add(data):
    """在项目库里随时加项目（不只首跑）。路径由「添加项目」的系统对话框给出。"""
    path = _clean_path(data.get("path"))
    whole = bool(data.get("whole"))
    if not path:
        return 400, {"ok": False, "error": "没给路径"}
    try:
        path = os.path.abspath(path)
    except (ValueError, OSError):
        return 400, {"ok": False, "error": "路径不合法"}
    if not os.path.isdir(path):
        return 400, {"ok": False, "error": "这个文件夹不存在：%s" % path}
    bad = _reject_bad_project_path(path)
    if bad:
        return 400, {"ok": False, "error": bad}
    with _CONF_LOCK:
        return _project_add_locked(path, whole)


def _project_add_locked(path, whole):
    conf = _load_conf()
    ws = list(conf.get("workspaces") or [])
    projects = list(conf.get("projects") or [])
    excluded = list(conf.get("excluded") or [])
    low = os.path.normcase(path)
    # 被移出过又重新添加：先把它从「已移出」里摘掉，否则加了也看不见
    excluded = [x for x in excluded if os.path.normcase(x) != low]
    if whole:
        if any(os.path.normcase(w) == low for w in ws):
            return 200, {"ok": True, "dup": True, "reason": "这个文件夹已经整个加过了"}
        ws.append(path)
        projects = [p for p in projects
                    if os.path.normcase(p) != low
                    and not os.path.normcase(p).startswith(low + os.sep)]
    else:
        if any(os.path.normcase(p) == low for p in projects):
            return 200, {"ok": True, "dup": True, "reason": "这个项目已经加过了"}
        if any(low == os.path.normcase(w) or low.startswith(os.path.normcase(w) + os.sep)
               for w in ws):
            # 它已经被某个「整个文件夹」罩着了；之前若被移出过，上面摘 excluded 就够了
            conf["excluded"] = excluded
            _save_conf(conf)
            build(load_roots(), ACTIVE_SITE)
            return 200, {"ok": True, "dup": True,
                         "reason": "它所在的文件夹已经整个加过了，现在已恢复显示"}
        projects.append(path)
    conf["workspaces"], conf["projects"], conf["excluded"] = ws, sorted(set(projects)), excluded
    conf["setup_done"] = True
    _save_conf(conf)
    d = build(load_roots(), ACTIVE_SITE)
    return 200, {"ok": True, "dup": False, "path": path,
                 "projects_now": len(d.get("projects", []))}


def api_project_remove(data):
    """把项目移出项目库。

    ⛔ 这里**只改灵台自己的配置，绝不碰用户的文件**。
    用户点「移除」时脑子里想的多半是「别在这儿显示了」，但也可能以为是删文件——
    所以按钮叫「移出项目库」不叫「删除」，返回值里也把「文件一个没动」说清楚。
    灵台永远不提供删除用户项目文件的功能，这条不给任何开关。
    """
    path = _clean_path(data.get("path"))
    if not path:
        return 400, {"ok": False, "error": "没给路径"}
    try:
        path = os.path.abspath(path)
    except (ValueError, OSError):
        return 400, {"ok": False, "error": "路径不合法"}
    with _CONF_LOCK:
        return _project_remove_locked(path)


def _project_remove_locked(path):
    conf = _load_conf()
    ws = list(conf.get("workspaces") or [])
    projects = list(conf.get("projects") or [])
    excluded = list(conf.get("excluded") or [])
    low = os.path.normcase(path)

    was_ws = any(os.path.normcase(w) == low for w in ws)
    ws = [w for w in ws if os.path.normcase(w) != low]
    before = len(projects)
    projects = [p for p in projects if os.path.normcase(p) != low]
    removed_direct = len(projects) < before
    # 来自工作区/装配图/sandbox 自动发现的，删不掉「来源」，只能记进排除单
    if not was_ws and not any(os.path.normcase(x) == low for x in excluded):
        excluded.append(path)
    conf["workspaces"], conf["projects"], conf["excluded"] = ws, projects, sorted(set(excluded))
    conf["setup_done"] = True
    _save_conf(conf)
    d = build(load_roots(), ACTIVE_SITE)
    still = any(os.path.normcase(p["path"]) == low for p in d.get("projects", []))
    return 200, {"ok": True, "path": path, "files_untouched": os.path.isdir(path),
                 "how": ("整个文件夹" if was_ws else ("单项" if removed_direct else "记入排除单")),
                 "still_listed": still, "projects_now": len(d.get("projects", []))}


def api_project_restore(data):
    """撤销移出——把它从排除单里拿回来。移错了要能一键回来。"""
    path = _clean_path(data.get("path"))
    if not path:
        return 400, {"ok": False, "error": "没给路径"}
    try:
        path = os.path.abspath(path)
    except (ValueError, OSError):
        return 400, {"ok": False, "error": "路径不合法"}
    with _CONF_LOCK:
        return _project_restore_locked(path)


def _project_restore_locked(path):
    conf = _load_conf()
    low = os.path.normcase(path)
    excluded = [x for x in (conf.get("excluded") or []) if os.path.normcase(x) != low]
    conf["excluded"] = excluded
    # 若它不在任何工作区底下，光摘排除单还不够，得把它作为单项加回来
    ws = list(conf.get("workspaces") or [])
    covered = any(low == os.path.normcase(w) or low.startswith(os.path.normcase(w) + os.sep)
                  for w in ws)
    projects = list(conf.get("projects") or [])
    if not covered and os.path.isdir(path) \
            and not any(os.path.normcase(p) == low for p in projects):
        projects.append(path)
    conf["projects"] = sorted(set(projects))
    _save_conf(conf)
    d = build(load_roots(), ACTIVE_SITE)
    back = any(os.path.normcase(p["path"]) == low for p in d.get("projects", []))
    return 200, {"ok": True, "path": path, "restored": back,
                 "projects_now": len(d.get("projects", []))}


def api_setup_state(_data):
    cur = {}
    if os.path.isfile(ACTIVE_ROOTS_FILE):
        try:
            with io.open(ACTIVE_ROOTS_FILE, encoding="utf-8") as f:
                cur = json.load(f) or {}
        except (OSError, ValueError):
            cur = {}
    return 200, {"ok": True, "drives": list_drives(), "home": os.path.expanduser("~"),
                 "default_depth": 3,
                 "workspaces": cur.get("workspaces") or [],
                 "projects": cur.get("projects") or [],
                 "excluded": cur.get("excluded") or []}


def _dir_evidence(p):
    """一个目录的「像不像项目」证据。不下判断，只摆事实。"""
    try:
        names = os.listdir(p)
    except OSError:
        return {"md": 0, "subs": 0, "installed": False, "signals": [], "readable": False}
    low = set(n.lower() for n in names)
    md = subs = 0
    for n in names:
        try:
            if os.path.isdir(os.path.join(p, n)):
                subs += 1
            elif n.lower().endswith(".md"):
                md += 1
        except OSError:
            continue
    installed = False
    if "brain" in low:
        try:
            installed = any(h in set(os.listdir(os.path.join(p, "brain"))) for h in ORGAN_HINT)
        except OSError:
            installed = False
    sig = []
    if installed:
        sig.append("已装六器官")
    if ".git" in low:
        sig.append("git")
    if "claude.md" in low or ".claude" in low:
        sig.append("接过 AI")
    if any(f in low for f in ENGINEER_FILES):
        sig.append("工程件")
    return {"md": md, "subs": subs, "installed": installed, "signals": sig, "readable": True}


_PICK_LOCK = threading.Lock()


def native_pick_folder(title="选择项目所在的文件夹"):
    """弹 Windows 原生「浏览文件夹」对话框，返回用户选的路径（取消返回 None）。

    ⛔ 三个坑，都是实测踩出来的：
      ① 64 位下必须声明 restype/argtypes——SHBrowseForFolderW 返回 LPITEMIDLIST 指针，
         ctypes 默认按 c_int 截断，传给 SHGetPathFromIDListW 直接 access violation。
      ② 必须在 BFFM_INITIALIZED 回调里 SetForegroundWindow，否则对话框会开在
         浏览器窗口后面，用户看不见还以为程序死了。
      ③ 每个线程都要 CoInitialize（HTTP handler 是线程池里的线程）。
    """
    if os.name != "nt":
        return None, "只有 Windows 有这个对话框"
    import ctypes
    import ctypes.wintypes as wt

    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32
    BIF_RETURNONLYFSDIRS, BIF_NEWDIALOGSTYLE, BFFM_INITIALIZED = 0x1, 0x40, 1

    class BROWSEINFO(ctypes.Structure):
        _fields_ = [("hwndOwner", wt.HWND), ("pidlRoot", ctypes.c_void_p),
                    ("pszDisplayName", wt.LPWSTR), ("lpszTitle", wt.LPCWSTR),
                    ("ulFlags", ctypes.c_uint), ("lpfn", ctypes.c_void_p),
                    ("lParam", wt.LPARAM), ("iImage", ctypes.c_int)]

    shell32.SHBrowseForFolderW.restype = ctypes.c_void_p
    shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(BROWSEINFO)]
    shell32.SHGetPathFromIDListW.restype = wt.BOOL
    shell32.SHGetPathFromIDListW.argtypes = [ctypes.c_void_p, wt.LPWSTR]
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]

    cbtype = ctypes.WINFUNCTYPE(ctypes.c_int, wt.HWND, ctypes.c_uint, wt.LPARAM, wt.LPARAM)

    def _cb(hwnd, msg, lp, data):
        if msg == BFFM_INITIALIZED:
            user32.SetForegroundWindow(hwnd)
            user32.SetWindowPos(hwnd, wt.HWND(-1), 0, 0, 0, 0, 0x0003)
            user32.SetWindowPos(hwnd, wt.HWND(-2), 0, 0, 0, 0, 0x0003)
        return 0

    cb = cbtype(_cb)
    ole32.CoInitialize(None)
    try:
        buf = ctypes.create_unicode_buffer(260)
        bi = BROWSEINFO()
        bi.hwndOwner = None
        bi.pidlRoot = None
        bi.pszDisplayName = ctypes.cast(buf, wt.LPWSTR)
        bi.lpszTitle = title
        bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE
        bi.lpfn = ctypes.cast(cb, ctypes.c_void_p)
        pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
        if not pidl:
            return None, None          # 用户点了取消
        path = ctypes.create_unicode_buffer(260)
        ok = shell32.SHGetPathFromIDListW(pidl, path)
        ole32.CoTaskMemFree(pidl)
        if not ok or not path.value:
            return None, "选中的不是一个文件夹路径（比如「此电脑」本身）"
        return path.value, None
    except Exception as e:                       # 兜底出声，不静默返回空
        return None, "对话框出错：%r" % (e,)
    finally:
        try:
            ole32.CoUninitialize()
        except Exception:
            pass


def api_pick_folder(data):
    """点「添加项目」→ 这里弹真正的系统对话框。请求会一直等到用户选完或取消。"""
    if not _PICK_LOCK.acquire(blocking=False):
        return 409, {"ok": False, "error": "已经有一个选择窗口开着了，先把它处理掉"}
    try:
        path, err = native_pick_folder(data.get("title") or "选择项目所在的文件夹")
    finally:
        _PICK_LOCK.release()
    if err:
        return 500, {"ok": False, "error": err}
    if not path:
        return 200, {"ok": True, "cancelled": True}
    ev = _dir_evidence(path)
    child = 0
    try:
        for e in os.scandir(path):
            if e.is_dir() and not e.name.startswith(".") and e.name.lower() not in SCAN_SKIP:
                c = _dir_evidence(e.path)
                if c["installed"] or c["md"] or c["subs"]:
                    child += 1
    except OSError:
        child = 0
    return 200, {"ok": True, "cancelled": False, "path": path,
                 "name": os.path.basename(path) or path,
                 "installed": ev["installed"], "signals": ev["signals"],
                 "md": ev["md"], "subs": ev["subs"], "child_candidates": child}


def _looks_like_project(names_low):
    return ("brain" in names_low or ".git" in names_low
            or any(e in names_low for e in ENGINEER_FILES))


def find_workspaces(locations, depth=3):
    """帮「忘了项目放哪」的人找**工作区**——不是找项目。

    ⛔ 判「这个目录是不是项目」不可靠（实测 36% 召回、11 误报，已弃掉）；
    但判「这个目录是不是装项目的柜子」是结构性的，可靠得多：柜子底下一层
    齐刷刷全是有内容的子目录。四条约束把候选从 191 压到 9，sandbox 排第一：
      ① 盘根不算——D:\\ 底下 44 个子目录，但它不是谁的工作区
      ② 柜子自己不是项目——Savant-Learn 有 brain+git，那是项目
      ③ 至少一个子目录带强信号——否则是 static\\video 那种 83 个 audio_xxx 的资源堆
      ④ 系统目录不进、软件安装目录靠边站
    """
    t0 = time.time()
    out, solo, seen = [], [], 0
    for base in locations:
        if not base or not os.path.isdir(base):
            continue
        stack = [(base, 0)]
        while stack and seen < 30000:
            d, dep = stack.pop()
            if dep > depth:
                continue
            try:
                entries = list(os.scandir(d))
            except OSError:
                continue
            seen += 1
            for e in entries:
                try:
                    if e.is_dir() and e.name.lower() not in SCAN_SKIP and not e.name.startswith("."):
                        stack.append((e.path, dep + 1))
                except OSError:
                    continue
            if dep == 0:
                continue
            try:
                names_low = set(x.lower() for x in os.listdir(d))
                subs = [e for e in os.scandir(d) if e.is_dir()
                        and not e.name.startswith(".") and e.name.lower() not in SCAN_SKIP]
            except OSError:
                continue
            # 散落在外的独立项目也要收——Savant-Learn 有 brain+git，是最确定的那种项目，
            # 上一版因「柜子自己不是项目」被排掉、又不在任何柜子里，从结果里彻底消失。
            # ⛔ 但「有 CLAUDE.md/.claude」不能算「自己是项目」：柜子也会有那份目录说明，
            #    照它判会把 sandbox 判成项目，底下 13 个真项目一起陪葬（实测过，别再犯）。
            inst = False
            if "brain" in names_low:
                try:
                    inst = any(o in set(os.listdir(os.path.join(d, "brain")))
                               for o in ORGAN_HINT)
                except OSError:
                    inst = False
            if inst or _looks_like_project(names_low):
                sig = []
                if inst:
                    sig.append("已装六器官")
                if ".git" in names_low:
                    sig.append("git")
                if "claude.md" in names_low or ".claude" in names_low:
                    sig.append("接过 AI")
                if any(x in names_low for x in ENGINEER_FILES):
                    sig.append("工程件")
                segs0 = [x.lower() for x in d.replace("/", "\\").split("\\")]
                solo.append({"path": d, "name": os.path.basename(d) or d,
                             "installed": inst, "signals": sig,
                             "software": any(x in SOFTWARE_SEG for x in segs0)})
                # 已装六器官 = 确定是项目，不必再问它是不是柜子；
                # 只有 .git/工程件的则两档并存，让人自己选当项目还是当工作区。
                if inst:
                    continue
                self_project = True
            else:
                self_project = False
            n = installed = git = ai = eng = 0
            names = []
            for s in subs:
                try:
                    inner = set(x.lower() for x in os.listdir(s.path))
                except OSError:
                    continue
                if not (any(x.endswith(".md") for x in inner) or len(inner) > 2):
                    continue
                n += 1
                if len(names) < 4:
                    names.append(s.name)
                if "brain" in inner:
                    try:
                        if any(o in set(os.listdir(os.path.join(s.path, "brain")))
                               for o in ORGAN_HINT):
                            installed += 1
                    except OSError:
                        pass
                if ".git" in inner:
                    git += 1
                if "claude.md" in inner or ".claude" in inner:
                    ai += 1
                if any(x in inner for x in ENGINEER_FILES):
                    eng += 1
            if n < 2 or (installed + git + ai + eng) == 0:
                continue
            segs = [x.lower() for x in d.replace("/", "\\").split("\\")]
            out.append({"path": d, "children": n, "installed": installed, "git": git,
                        "ai": ai, "eng": eng, "sample": names,
                        "self_project": self_project,
                        "software": any(x in SOFTWARE_SEG for x in segs)})
    # 排序：软件目录垫底；「自己也像项目」的（ruflow、ComfyUI 这种）往后排——
    # 它们更可能是项目本身而不是装项目的柜子；纯柜子（sandbox）该排最前。
    out.sort(key=lambda x: (x["software"], x["self_project"], -x["installed"],
                            -(x["git"] + x["ai"] + x["eng"]), -x["children"]))
    # 已经被某个候选工作区罩住的独立项目，不用再单列一遍
    ws_low = [os.path.normcase(w["path"]) + os.sep for w in out]
    solo = [s for s in solo
            if not any(os.path.normcase(s["path"]).startswith(w) for w in ws_low)]
    solo.sort(key=lambda x: (x["software"], not x["installed"], -len(x["signals"]), x["path"]))
    return {"workspaces": out, "projects": solo, "scanned": seen,
            "ms": int((time.time() - t0) * 1000)}


def api_find_projects(data):
    """扫一遍，直接给出**项目候选清单**——不让人先去理解「工作区」是什么。

    内部还是先找柜子再展开（柜子判据可靠、项目判据不可靠），但那是实现细节，
    界面上只呈现「这些可能是你的项目，按所在文件夹分好组，勾就行」。
    """
    locs = [str(x) for x in (data.get("locations") or []) if str(x).strip()]
    if not locs:
        locs = [d["path"] for d in list_drives() if d["default"]]
    bad = [p for p in locs if not os.path.isdir(p)]
    if bad:
        return 400, {"ok": False, "error": "这些位置不存在：%s" % "、".join(bad[:3])}
    try:
        depth = max(1, min(int(data.get("depth", 3)), 5))
    except (TypeError, ValueError):
        depth = 3
    r = find_workspaces(locs, depth)

    groups, seen = [], set()

    def ev_of(p):
        e = _dir_evidence(p)
        return {"path": p, "name": os.path.basename(p) or p,
                "installed": e["installed"], "signals": e["signals"],
                "md": e["md"], "subs": e["subs"]}

    for w in r["workspaces"]:
        # ⛔ 「自己也像项目」的不展开：ComfyUI/ruflow/nexus_ai 有 .git 或工程件，
        # 展开它们等于把项目的内部结构（api_server、docker、migrations…）当项目列出来，
        # 清单一下子从 40 涨到 160。它们本身已经在「单独放在外面」那档里了。
        if w.get("self_project"):
            continue
        items = []
        try:
            for e in sorted(os.scandir(w["path"]), key=lambda x: x.name):
                if not e.is_dir() or e.name.startswith(".") or e.name.lower() in SCAN_SKIP:
                    continue
                key = os.path.normcase(e.path)
                if key in seen:
                    continue
                seen.add(key)
                items.append(ev_of(e.path))
        except OSError:
            continue
        if items:
            items.sort(key=lambda x: (not x["installed"], -len(x["signals"]), x["name"]))
            groups.append({"parent": w["path"], "kind": "folder", "count": len(items),
                           "installed_n": sum(1 for i in items if i["installed"]),
                           "software": w["software"], "items": items})
    solo = []
    for s in r.get("projects", []):
        key = os.path.normcase(s["path"])
        if key in seen:
            continue
        seen.add(key)
        solo.append(ev_of(s["path"]))
    if solo:
        solo.sort(key=lambda x: (not x["installed"], -len(x["signals"]), x["name"]))
        groups.append({"parent": "", "kind": "solo", "count": len(solo),
                       "installed_n": sum(1 for i in solo if i["installed"]),
                       "software": False, "items": solo})
    groups.sort(key=lambda g: (g["software"], g["kind"] == "solo",
                               -g["installed_n"], -g["count"]))
    total = sum(g["count"] for g in groups)
    return 200, {"ok": True, "groups": groups, "total": total,
                 "scanned": r["scanned"], "ms": r["ms"]}


def api_browse(data):
    """目录浏览器。⛔ 浏览器拿不到系统文件夹对话框（webkitdirectory 只给相对路径），
    所以自己做一个——而且顺手把「这个目录下有几个像项目的子目录」算出来，
    选工作区时一眼就能认：项目容器底下一层通常齐刷刷全是候选。"""
    path = (data.get("path") or "").strip()
    if not path:  # 根层：列盘符
        return 200, {"ok": True, "path": "", "parent": None, "crumbs": [],
                     "dirs": [{"name": d["path"], "path": d["path"], "kind": d["kind"],
                               "label": d["label"], "md": 0, "subs": 0,
                               "installed": False, "signals": [], "candidates": None}
                              for d in list_drives()]}
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return 400, {"ok": False, "error": "目录不存在：%s" % path}
    try:
        entries = sorted(e for e in os.listdir(path)
                         if not e.startswith(".") and e.lower() not in SCAN_SKIP)
    except OSError as e:
        return 400, {"ok": False, "error": "读不了这个目录：%s" % e}
    dirs, files, cand = [], [], 0
    for name in entries:
        p = os.path.join(path, name)
        if os.path.isdir(p):
            ev = _dir_evidence(p)
            if ev["installed"] or ev["md"] or ev["subs"]:
                cand += 1
            dirs.append({"name": name, "path": p, "kind": "dir", "label": "",
                         "md": ev["md"], "subs": ev["subs"],
                         "installed": ev["installed"], "signals": ev["signals"],
                         "candidates": None})
        elif os.path.isfile(p):
            # 也列文件——像资源管理器那样能看清里面有什么，才判断得出这是不是项目
            try:
                sz = os.path.getsize(p)
            except OSError:
                sz = 0
            files.append({"name": name, "size": sz})
    crumbs, cur = [], path
    while True:
        crumbs.insert(0, {"name": os.path.basename(cur) or cur, "path": cur})
        nxt = os.path.dirname(cur)
        if not nxt or nxt == cur:
            break
        cur = nxt
    self_ev = _dir_evidence(path)
    return 200, {"ok": True, "path": path, "parent": os.path.dirname(path) or None,
                 "crumbs": crumbs, "dirs": dirs, "files": files[:60],
                 "file_total": len(files),
                 "child_candidates": cand, "self": self_ev}


def _regen_cmd(brain_dir=None):
    """收工重算状态该敲什么——按**当前形态**给，不按作者的形态给。

    ⛔ 冻结态绝不许发 `python -X utf8 状态生成器.py`。
       用户手上一定有 exe，不一定有 python.exe——这正是 _run_generator 为了
       「零依赖」亲手绕开的东西（见那里的注释）。产品自己绕开的依赖，
       不能转头写进发给用户的说明书；这跟「报错叫人去跑他根本没有的
       install.py」是同一类错，那次已经付过一次代价了。
    """
    if _FROZEN:
        exe = os.path.abspath(sys.executable)
        if brain_dir:
            return '在命令行跑 "%s" --regen "%s"（或回驾驶舱项目页点「🔄 重算状态」）' % (exe, brain_dir)
        return '跑 lingtaios.exe --regen <项目目录>（或回驾驶舱项目页点「🔄 重算状态」）'
    if brain_dir:
        return "跑 python -X utf8 状态生成器.py（在 %s 目录）" % brain_dir
    return "跑 python -X utf8 状态生成器.py"


def _run_generator(brain_dir):
    """用 skills 真源直跑任意项目（v0.7 共享化：--dir，项目副本只是快照）。"""
    gen = os.path.join(REPO, "project-delivery", "scaffold", "状态生成器.py")
    if not os.path.isfile(gen):
        return {"error": "生成器真源不在：%s" % gen}

    if _FROZEN:
        # ⛔ 打包后 sys.executable 是 lingtaios.exe 自己，不是 python.exe——
        # 拿它当解释器去跑生成器，参数不认、输出编码也对不上（0xc9/GBK 撞 utf-8 解码）。
        # 而「零依赖」意味着不能改成去找系统 Python：用户机器上可能根本没有。
        # → 进程内执行。生成器无 chdir 副作用，只需借走 argv 和 stdout。
        import contextlib
        import runpy
        buf = io.StringIO()
        argv_bak = sys.argv[:]
        sys.argv = [gen, "--dir", brain_dir]
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                runpy.run_path(gen, run_name="__main__")
            code = 0
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        except Exception as e:  # 生成器炸了要出声，不许静默返空
            return {"exit": 1, "out": buf.getvalue()[-2000:], "err": repr(e)[:500]}
        finally:
            sys.argv = argv_bak
        return {"exit": code, "out": buf.getvalue()[-2000:], "err": ""}

    try:
        # errors="replace"：子进程若按 GBK 吐中文，不许把解码异常炸到调用方
        r = subprocess.run([sys.executable, "-X", "utf8", gen, "--dir", brain_dir],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"error": str(e)}
    return {"exit": r.returncode, "out": (r.stdout or "")[-2000:], "err": (r.stderr or "")[-500:]}


# 通用件 = 纯工具件（skills 升了必须传播）。⚠ 规则台账/关口清单是**项目专属数据**
# （AI 会往里立条/打勾，同步会覆盖真数据——2026-08-16 演练差点覆掉 IPGuard 的 R-001/R-002）
COMMON_FILES = ["状态生成器.py"]
SYNC_EXTRA = ["README.md"]  # 项目里有就一并同步（纯说明件）


def _md5(p):
    try:
        with open(p, "rb") as f:
            import hashlib
            return hashlib.md5(f.read()).hexdigest()
    except OSError:
        return None


def sync_probe(projects):
    """通用件 md5 对比：skills scaffold vs 各项目 brain。返回落后清单。"""
    scaffold = os.path.join(REPO, "project-delivery", "scaffold")
    out = []
    for p in projects:
        brain = os.path.join(p["path"], "brain")
        if not os.path.isdir(brain):
            continue
        outdated = []
        for f in COMMON_FILES + SYNC_EXTRA:
            src = os.path.join(scaffold, f)
            dst = os.path.join(brain, f)
            if not os.path.isfile(dst):
                continue  # 项目没有该件，不算落后（新装项目按需补）
            if _md5(src) != _md5(dst):
                outdated.append(f)
        p["outdated"] = outdated
        if outdated:
            out.append({"project": p["name"], "path": p["path"], "outdated": outdated})
    return out


def api_refresh(data):
    """深查：重算全部真源（快照 vs 深查，抄 OpenClaw 状态分档）。"""
    try:
        d = build(load_roots(), ACTIVE_SITE)
        return 200, d
    except Exception as e:
        return 500, {"ok": False, "error": str(e)}


def api_sync_project(data):
    """一键同步通用件：覆盖项目 brain 的通用件，专属件零接触。"""
    path = (data.get("path") or "").strip()
    brain = os.path.join(path, "brain")
    if not os.path.isdir(brain):
        return 400, {"ok": False, "error": "没有 brain\\ 目录"}
    scaffold = os.path.join(REPO, "project-delivery", "scaffold")
    n = 0
    for f in COMMON_FILES + SYNC_EXTRA:
        src = os.path.join(scaffold, f)
        dst = os.path.join(brain, f)
        if os.path.isfile(src) and os.path.isfile(dst) and _md5(src) != _md5(dst):
            shutil.copyfile(src, dst)
            n += 1
    try:
        build(load_roots(), ACTIVE_SITE)
    except Exception:
        pass
    return 200, {"ok": True, "synced": n}


def api_apply_seed_update(data):
    """把「认不出来历」的出厂文件换成新版。⛔ 覆盖前一律先留 .bak。

    只处理 _seed_repo 记在 pending 里的那些（v0.2.0 及更早装的，台账里没有）。
    用户明确改过的（kept）不在这里，也不给入口——那条红线不给开关。
    """
    if not BUNDLE:
        return 400, {"ok": False, "error": "源码态没有出厂副本可换"}
    want = [k for k in (data.get("files") or []) if isinstance(k, str)]
    if not want:
        return 400, {"ok": False, "error": "没选任何文件"}
    state = _seed_state()
    allowed = set(state.get("pending") or [])
    bad = [k for k in want if k not in allowed]
    if bad:
        return 400, {"ok": False, "error": "这些不在待定清单里，不许动：%s" % "、".join(bad[:5])}
    known = dict(state.get("files") or {})
    done, failed = [], []
    for key in want:
        src = os.path.join(BUNDLE, key.replace("/", os.sep))
        dst = os.path.join(REPO, key.replace("/", os.sep))
        if not os.path.isfile(src) or not os.path.isfile(dst):
            failed.append(key)
            continue
        try:
            shutil.copyfile(dst, dst + ".bak")   # 先留退路，再覆盖
            shutil.copyfile(src, dst)
            known[key] = _md5(dst)
            done.append(key)
        except OSError:
            failed.append(key)
    state["files"] = known
    state["pending"] = [k for k in (state.get("pending") or []) if k not in done]
    try:
        with io.open(SEED_MANIFEST, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        return 500, {"ok": False, "error": "台账写不了：%s" % e}
    try:
        build(load_roots(), ACTIVE_SITE)
    except Exception:
        pass
    return 200, {"ok": True, "updated": done, "failed": failed}


def api_run_generator(data):
    path = (data.get("path") or "").strip()
    if not path or not os.path.isdir(path):
        return 400, {"ok": False, "error": "项目路径不存在"}
    roots = load_roots()
    rej = _reject_sandbox(os.path.abspath(path), roots)
    if rej:
        return rej
    brain = os.path.join(path, "brain")
    if not os.path.isdir(brain):
        return 400, {"ok": False, "error": "没有 brain\\ 目录（先装六器官）"}
    gen = _run_generator(brain)
    ok = gen.get("exit") == 0
    return 200 if ok else 500, {"ok": ok, "generator": gen}


def _read_md(p):
    try:
        with io.open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def api_project_detail(data):
    """项目详情：只读渲染六器官 + 交接 + 继续做指令。sandbox 项目只读查看是允许的。"""
    path = (data.get("path") or "").strip()
    if not path or not os.path.isdir(path):
        return 400, {"ok": False, "error": "项目路径不存在"}
    brain = os.path.join(path, "brain")
    detail = {"ok": True, "name": os.path.basename(path), "path": path,
              "has_brain": os.path.isdir(brain)}

    organs = {}
    for f in ORGANS:
        organs[f] = os.path.isfile(os.path.join(brain, f))
    detail["organs"] = organs

    # 器官文档渲染（脑内文件 = 安全的项目文档）
    docs = {}
    for key, rel in (("宪法", "00_宪法.md"), ("法典", "01_法典.md"), ("状态", "02_状态.md"),
                     ("在建", "03_在建.md"), ("待办", "04_待办池.md"), ("交接", "05_交接.md"),
                     ("关口清单", "关口清单.md")):
        p = os.path.join(brain, rel)
        if os.path.isfile(p):
            docs[key] = mdlite.render(_read_md(p))
    handoff = os.path.join(path, "HANDOFF.md")
    if os.path.isfile(handoff):
        docs["HANDOFF"] = mdlite.render(_read_md(handoff))
    detail["docs"] = docs

    # 进度摘要：03_在建 的注标题（= 进行中的事）+ 05_交接 的做完/没做完
    notes = []
    plan_p = os.path.join(brain, "03_在建.md")
    if os.path.isfile(plan_p):
        text = _read_md(plan_p) or ""
        for m in re.finditer(r"^###\s+(注-\d+\s*·\s*.+)$", text, re.M):
            title = m.group(1).strip()
            if "· <" not in title:
                notes.append(title)
    detail["notes"] = notes
    detail["handoff_done"] = ""
    detail["handoff_blank"] = False
    hand_p = os.path.join(brain, "05_交接.md")
    if os.path.isfile(hand_p):
        t = _read_md(hand_p) or ""
        m = re.search(r"## 本窗做完的 / 没做完的(.*?)(?=\n## |\Z)", t, re.S)
        if m:
            # ⛔ 刚建好的项目，这一段还是出厂模板：「做完：<...>」「熔断了吗：<到期没做
            #    完的注…>」。原样渲染出来，它长得**像内容**——陌生人第一次点进自己刚建的
            #    项目，看到的是一屏尖括号，第一反应是"这东西坏了/我漏填了什么"。
            #    模板占位符是给填的人看的提示，不是状态。认出来就别当状态展示。
            detail["handoff_blank"] = "<...>" in m.group(1)
            detail["handoff_done"] = mdlite.render(m.group(1))

    # 根级 md 只列名不渲染（旧项目文档内容不可预知，守"涉密不渲染"红线）
    try:
        detail["root_md"] = sorted(e for e in os.listdir(path)
                                   if e.lower().endswith(".md") and os.path.isfile(os.path.join(path, e)))
    except OSError:
        detail["root_md"] = []

    # 告警
    alarms = []
    detail["state_at"], detail["state_age_days"] = "", None
    sj = os.path.join(brain, "02_状态.json")
    if os.path.isfile(sj):
        try:
            with io.open(sj, encoding="utf-8") as f:
                _sd = json.load(f)
            alarms = _sd.get("alarms", [])
            detail["state_at"] = _sd.get("at", "")
            # 详情页也要知道这份状态多老——见 discover_projects 里那段注释：
            # 旧快照报平安，比没有状态更危险。
            if detail["state_at"]:
                try:
                    detail["state_age_days"] = int((time.time() - time.mktime(
                        time.strptime(detail["state_at"], "%Y-%m-%d %H:%M:%S"))) // 86400)
                except ValueError:
                    pass
        except (ValueError, OSError):
            alarms = ["02_状态.json 解析失败"]
    detail["alarms"] = alarms

    # 继续做指令（按项目真实路径生成，含收窗写回——进度必须流回驾驶舱）
    card = os.path.join(HERE, "AI开窗必读.md")
    # 历史文档提示：续装项目的真实进度在根目录交接/施工图里，必须点名，否则 AI 读到的是空模板
    def _mtime(f):
        try:
            return os.path.getmtime(os.path.join(path, f))
        except OSError:
            return 0
    hand_names = sorted(
        (f for f in detail["root_md"] if re.search(r"交接|施工|回执|复盘|纪要|HANDOFF|进度", f, re.I)),
        key=_mtime, reverse=True)
    root_hint = ("先读项目根的交接/施工图文档（最新在前，如：%s），" % "、".join(hand_names[:5])) if hand_names else ""
    if detail["has_brain"]:
        hand_p = os.path.join(brain, "05_交接.md")
        step2 = ("%s再读 %s 和 %s，告诉我：现在到哪了、下一步是什么" % (
            root_hint, os.path.join(brain, "01_法典.md"), hand_p))
        seg = "立刻把「做到哪 / 下一步」更新进 %s" % hand_p
        close_step = ("更新 %s（做完的/没做完的），然后%s——"
                      "下次双击驾驶舱，进度自动反映") % (hand_p, _regen_cmd(brain))
    else:
        step2 = ("读 %s 里的交接/施工图文档（文件名见驾驶舱项目详情页），告诉我：现在到哪了、下一步是什么" % path)
        seg = "立刻把「做到哪 / 下一步」追加写进 %s" % handoff
        close_step = ("把「做完的 / 没做完的 / 下一步」追加写进 %s（没有就新建）——"
                      "下次双击驾驶舱，详情页就能看到进度") % handoff
    if detail["has_brain"]:
        trace_file = os.path.join(brain, "traces", time.strftime("%Y-%m-%d") + ".jsonl")
        trace_step = ("每完成一段，把「做了什么 / 证据 / 结果」追加一行到 %s"
                      "（一行 JSON：{\"t\":时间,\"act\":动作,\"ev\":证据,\"res\":结果}；目录不存在就建）" % trace_file)
    else:
        trace_step = None
    steps = [
        "项目：%s（%s）" % (detail["name"], path),
        "1. 先读 %s（AI开窗必读，照做开窗五步）" % card,
        "2. %s" % step2,
        "3. 每完成一个完整任务段，%s（不要等收窗；我随时会离开，进度必须在文件里）" % seg,
    ]
    if trace_step:
        steps.append("4. %s" % trace_step)
    n = len(steps)          # 已有几步，后面接着编号，别写死 4/5/6
    steps.append("%d. 每段回复第一行打证据头；不可逆动作先出施工图等我拍板" % n)
    # ⛔ 「用的人越多方法越准」这句话，瓶颈从来不在人愿不愿意，而在**麻烦**：
    #    判断一条坑通不通用、写成规范格式、开个 issue——90% 的人不会为别人多走这几步
    #    （90-9-1 定律）。但灵台的用户不是一个人，是「人 + AI」，而 AI 不嫌麻烦。
    #    所以把判断和起草都交给 AI，人只剩下「看一眼、点一下」。
    draft = os.path.join(path, "贡献草稿.md")
    steps.append(
        "%d. 这次要是踩了新坑：按「一句话坑 / 防法（照做即可）/ 失效判据（防的事被结构性"
        "消除即删）」记进本项目的经验记录。记完再自问一句——**换一个项目、换一套技术栈，"
        "这条还成立吗？** 成立的，另外追加一份到 %s（同样三段格式），收工时告诉我"
        "「有几条可以贡献回主库」。只在本项目成立的不用写，留着自己用就行。"
        % (n + 1, draft))
    steps.append("%d. 收工时：%s" % (n + 2, close_step))
    detail["resume"] = "\n".join(steps)
    # 通用件落后检测（v0.7 升级传播）
    scaffold = os.path.join(REPO, "project-delivery", "scaffold")
    detail["outdated"] = [
        f for f in COMMON_FILES + SYNC_EXTRA
        if os.path.isfile(os.path.join(brain, f)) and os.path.isfile(os.path.join(scaffold, f))
        and _md5(os.path.join(brain, f)) != _md5(os.path.join(scaffold, f))
    ]
    # 轨迹（自进化原料）：详情页展示最近 20 行
    detail["traces"] = _read_traces(brain)
    return 200, detail


def _read_traces(brain, limit=20):
    """读 brain/traces/ 最近的轨迹行（倒序，最多 limit 行）。"""
    tdir = os.path.join(brain, "traces")
    if not os.path.isdir(tdir):
        return []
    files = sorted((f for f in os.listdir(tdir) if f.endswith(".jsonl")), reverse=True)
    lines = []
    for f in files:
        try:
            with io.open(os.path.join(tdir, f), encoding="utf-8", errors="replace") as fh:
                lines.extend(fh.read().strip().split("\n"))
        except OSError:
            continue
        if len(lines) >= limit:
            break
    out = []
    for ln in reversed(lines[:limit]):
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except ValueError:
            out.append({"raw": ln[:120]})
    return out


def api_open_dir(data):
    """在资源管理器打开项目目录（只读动作，不写任何文件）。"""
    path = (data.get("path") or "").strip()
    if not path or not os.path.isdir(path):
        return 400, {"ok": False, "error": "项目路径不存在"}
    try:
        os.startfile(path)
        return 200, {"ok": True}
    except OSError as e:
        return 500, {"ok": False, "error": str(e)}


def resolve(path_alias, roots):
    """{SKILLS}/{NEXUS}/{D}/{HOME} → 绝对路径。根缺失返回 None。"""
    m = re.match(r"\{([A-Z]+)\}(.*)$", path_alias)
    if not m:
        return path_alias  # 已无别名（相对段）保持原样
    alias, rest = m.group(1), m.group(2)
    root = REPO if alias == "SKILLS" else roots.get(alias)
    if not root:
        return None
    return os.path.normpath(os.path.join(root, rest.lstrip("\\/")))


def _cell_first_of(path_alias):
    return path_alias.lstrip("`").rstrip("`").strip()


def parse_map(text, roots):
    """解析 装配图 §1 七层表 + §4 逐文件清单 → layers, sources。"""
    layers = []
    rows = mdlite.table_rows(text, "1 · 七层总表")
    for r in rows:
        if r.get("层"):
            layers.append(r)

    sources = []
    cur_layer = None
    lines = text.split("\n")
    for ln in lines:
        m = re.match(r"^###\s+(L\d)\s", ln)
        if m:
            cur_layer = m.group(1)
    # 表格按小节归属：重扫，跟踪最近的 ### L 行
    # 段标题里的「本机专属」整层生效（L5 业务脑 / L6 项目层 / L7 归档层）；
    # 个别行另用性质列的 ·本机专属 单标（如 {HOME}/.claude/CLAUDE.md）。
    layer_local_only = {}
    for ln in lines:
        m = re.match(r"^###\s+(L\d)(.*)$", ln)
        if m:
            layer_local_only[m.group(1)] = "本机专属" in m.group(2)
    i, n = 0, len(lines)
    rows_by_layer = {}
    while i < n:
        m = re.match(r"^###\s+(L\d)", lines[i])
        if m:
            cur_layer = m.group(1)
            i += 1
            continue
        if cur_layer and lines[i].strip().startswith("|") and i + 1 < n:
            header = mdlite._split_row(lines[i])
            if "文件" in header and ("性质" in header):
                sec = []
                j = i + 1
                if j < n and mdlite._is_sep(mdlite._split_row(lines[j])):
                    j += 1
                while j < n and lines[j].strip().startswith("|"):
                    sec.append(mdlite._split_row(lines[j]))
                    j += 1
                if sec:
                    rows_by_layer.setdefault(cur_layer, []).append((header, sec))
                i = j
                continue
        i += 1

    for layer, groups in rows_by_layer.items():
        for header, sec in groups:
            for cells in sec:
                d = dict(zip(header, cells + [""] * max(0, len(header) - len(cells))))
                # 单元格里「`路径` 尾注」并存，只取反引号内的 token；一格多路径逐个登记
                tokens = re.findall(r"`([^`]*)`", d.get("文件", ""))
                alias_dir = None
                for raw in tokens:
                    raw = raw.strip()
                    if not raw or raw in ("—", "-"):
                        continue
                    if not (raw.startswith("{") or ":" in raw or "/" in raw or "\\" in raw):
                        # 裸名继承同格上一个文件的别名目录（如 `A.md`、`B.md`）
                        raw = (alias_dir or "{%s}/" % layer2alias(layer)) + raw
                    nature = d.get("性质", "")
                    # 「仅源码态」：灵台自身的源码/本机配置。exe 形态下用户手里只有 exe，
                    # 这些路径本就不存在——登记它们只有两种结局：一堆假 missing，
                    # 或者像 v0.1.1 那样把源码塞进包换假 ok（508MB 体积 + 量具照自己）。
                    # 所以 frozen 时直接不登记：分母只算「这个形态下真该在位的东西」。
                    if _FROZEN and "仅源码态" in nature:
                        continue
                    resolved = resolve(raw, roots)
                    if resolved is None:
                        status = "noroot"
                    else:
                        status = _status(resolved)
                        # 「本机专属」件（业务脑/项目/归档/用户自己的 AI 配置）不随灵台分发，
                        # 别人的机器上本来就没有 → 不在时标 absent（本机无此件），不算断头。
                        # ⛔ 只豁免「不在」；文件在就照常判——自己的机器一条都不放过。
                        if status == "missing" and (
                                layer_local_only.get(layer) or "本机专属" in nature):
                            status = "absent"
                    sources.append({
                        "layer": layer,
                        "path": raw,
                        "resolved": resolved or "",
                        "nature": nature,
                        "note": d.get("备注", ""),
                        "status": status,
                    })
                    if os.path.splitext(raw)[1]:
                        m = re.match(r"^(\{[A-Z]+\}/.*)/[^/]+$", raw)
                        if m:
                            alias_dir = m.group(1) + "/"
    return layers, sources


def layer2alias(layer):
    return {"L1": "SKILLS", "L2": "SKILLS", "L3": "SKILLS", "L4": "SKILLS",
            "L8": "SKILLS"}.get(layer, "NEXUS" if layer == "L5" else "NEXUS")


def _status(path):
    if not path:
        return "missing"
    p = path.rstrip("\\/")
    if os.path.isdir(p) or os.path.isfile(p):
        return "ok"
    return "missing"


def health_check(sources):
    missing = [s for s in sources if s["status"] == "missing" and s["resolved"]]
    noroot = [s for s in sources if s["status"] == "noroot"]
    absent = [s for s in sources if s["status"] == "absent"]
    ok = [s for s in sources if s["status"] == "ok"]

    # 同名双份 diff 扫描（登记路径去重后，同一 basename 的**不同文件**两两比对是否字节相同）
    from collections import defaultdict
    by_name = defaultdict(set)
    for s in sources:
        if s["status"] == "ok" and os.path.isfile(s["resolved"]):
            by_name[os.path.basename(s["resolved"])].add(os.path.normcase(s["resolved"]))
    identical = []
    for name, pathset in by_name.items():
        paths = sorted(pathset)
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                try:
                    same = open(paths[i], "rb").read() == open(paths[j], "rb").read()
                except OSError:
                    continue
                if same:
                    identical.append({"a": paths[i], "b": paths[j]})
    return {
        "total": len(sources), "ok": len(ok),
        # 状态环的分母：这台机器**该有**的 = 登记总数 − 无根 − 本机无此件。
        # 用 total 当分母会把「别人机器上本来就没有的东西」算成缺件：
        # 陌生人首开曾显示 10/59，其中 34 无根 15 本机件，真正该有的其实全在位。
        "applicable": len(sources) - len(noroot) - len(absent),
        "missing": [{"layer": s["layer"], "path": s["path"], "resolved": s["resolved"]} for s in missing],
        "noroot": len(noroot), "noroot_paths": [s["path"] for s in noroot],
        "absent": len(absent), "absent_paths": [s["path"] for s in absent],
        "identical_pairs": identical,
    }


def discover_projects(roots, sources):
    """发现规则：sandbox 深度 1 凡含 ≥1 个 .md 即算项目；D 盘只认装配图登记过的目录
    （单一权威源——D 盘根目录噪声多，不瞎扫）。缺器官的项目如实显示，不上器官数。"""
    EXCLUDE = ("node_modules", "__pycache__", "docs", "reference", "textbooks",
               "_archive", "site", "vendor", "web", "brain")
    found = {}

    def has_md(p):
        try:
            return any(e.lower().endswith(".md") and os.path.isfile(os.path.join(p, e))
                       for e in os.listdir(p))
        except OSError:
            return False

    def scan(base, require_md=True):
        """require_md=False 用于「用户指认的工作区」：底下一层全收。
        要求含 md 会漏掉真项目——sandbox 里的 nexus（12 子目录+git+工程件）
        就因为根目录没有 .md 一直没被收进来。不该由文件类型替用户决定。"""
        if not base or not os.path.isdir(base):
            return
        try:
            entries = os.listdir(base)
        except OSError:
            return
        for e in sorted(entries):
            if e.startswith(".") or e in EXCLUDE:
                continue
            p = os.path.join(base, e)
            if os.path.isdir(p) and (not require_md or has_md(p)):
                found[os.path.normpath(p).lower()] = p

    scan(os.path.join(roots.get("NEXUS"), "sandbox") if roots.get("NEXUS") else None)
    # D 盘项目 = 装配图 L6 登记的 {D}/ 行（单一权威源：图说谁是项目，谁就是）
    for s in sources:
        if s["layer"] == "L6" and s["path"].startswith("{D}/"):
            p = (s["resolved"] or "").rstrip("\\/")
            if os.path.isdir(p):
                found[os.path.normpath(p).lower()] = p
    # 工作区：用户指认「我的项目放这儿」，底下一层全是项目。
    # ⛔ 不猜——实测任何基于文件特征的判据都又漏又误：本机 105 个 md 的真项目
    # 一个工程信号都没有，而有全套工程信号的 ruflow\v2、nexus_ai_backup 又不是独立项目。
    # VS Code / JetBrains 同样不猜，都要用户显式指定目录。
    # 路径不可达的（外接盘拔了/网络盘断了/目录挪了）必须出声，不许静默吞掉。
    unreachable = []
    for ws in roots.get("_workspaces", []):
        if os.path.isdir(ws):
            scan(ws, require_md=False)
        else:
            unreachable.append(ws)
    for p in roots.get("_projects", []):
        if os.path.isdir(p):
            found[os.path.normpath(p).lower()] = p
        else:
            unreachable.append(p)
    discover_projects.unreachable = unreachable
    # 驾驶舱自己：**装了六器官才算项目**。
    # ⛔ 源码态 HERE 是 brain-console（真有 brain/，第一个吃自己狗粮的项目）；
    #    exe 形态下 HERE 是 exe 所在目录——放 dist\ 就冒出个叫「dist」的项目，
    #    放桌面就冒出「Desktop」。实测过：项目库里真多了一条 dist。
    if os.path.isdir(os.path.join(HERE, "brain")):
        found[os.path.normpath(HERE).lower()] = HERE
    # 排除单放最后：否则「驾驶舱自己」这条移出去了又会被重新塞回来
    for x in roots.get("_excluded", []):      # 工作区里但你说不算项目的
        found.pop(os.path.normpath(x).lower(), None)

    projects = []
    for p in found.values():
        organs = {}
        for o in ORGANS:
            organs[o] = os.path.isfile(os.path.join(p, "brain", o))
        alarms, state, at = [], None, ""
        sj = os.path.join(p, "brain", "02_状态.json")
        if os.path.isfile(sj):
            try:
                with io.open(sj, encoding="utf-8") as f:
                    d = json.load(f)
                alarms = d.get("alarms", [])
                at = d.get("at", "")
                state = "generated"
            except (ValueError, OSError):
                state = "bad_json"
        elif os.path.isfile(os.path.join(p, "brain", "状态源.json")):
            state = "not_run"
        # ⛔ 「状态已生成」是个不带时间的说法，一年前生成的和刚生成的长得一模一样。
        #    实测代价：本项目自己的 02_状态.md 停在 2026-08-16 03:52，写着
        #    「坑库 38 条 ✅ 无告警」，而真源当时已经 80 条——驾驶舱顶着一份
        #    28 小时前的旧快照报平安，漂了 42 条没有任何东西出声。
        #    根因是那时没有重算入口（界面没有，文档给的办法要 Python）。
        #    入口补上了还不够：**没人告诉你该按**，按钮就等于不存在。
        age_days = None
        if at:
            try:
                age_days = int((time.time() - time.mktime(
                    time.strptime(at, "%Y-%m-%d %H:%M:%S"))) // 86400)
            except ValueError:
                age_days = None
        handoff = os.path.join(p, "HANDOFF.md")
        projects.append({
            "name": os.path.basename(p),
            "path": p,
            "organs": organs,
            "alarms": alarms,
            "state": state,
            "state_at": at,
            "state_age_days": age_days,
            "handoff_mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(handoff))) if os.path.isfile(handoff) else "",
        })
    projects.sort(key=lambda x: x["name"])
    return projects


def build(roots, out_dir):
    with io.open(MAP, encoding="utf-8") as f:
        map_text = f.read()
    with io.open(PITFALL, encoding="utf-8") as f:
        pit_text = f.read()

    layers, sources = parse_map(map_text, roots)
    health = health_check(sources)
    projects = discover_projects(roots, sources)

    pit_sections, pit_rows = [], []
    columns = []
    for sec in PITFALL_SECTIONS:
        rows = mdlite.table_rows(pit_text, sec)
        pit_sections.append({"name": sec, "count": len(rows)})
        for r in rows:
            r["__section"] = sec
            pit_rows.append(r)
        if rows and not columns:
            columns = list(rows[0].keys())

    # 只登记「四篇方法论在不在、在哪」，**不再把全文渲染成 HTML 塞进 data.json**。
    # 界面上的「方法」页已经去掉了——那四篇是给 AI 读的文件，不是给人在网页里翻的，
    # 而渲染出来的 HTML 占了 data.json 的 92.2 / 111.4 KB（83%），每次开页面白传一遍。
    # 想看/想改的人走 设置 →「换机 / 我的文件」，那里给路径和「打开目录」按钮。
    methods = []
    for name, path in METHOD_DOCS:
        methods.append({"name": name, "path": path, "ok": os.path.isfile(path)})

    evolution = evolution_data(projects, pit_rows, health)
    sync = sync_probe(projects)

    root_status = []
    for alias in ("SKILLS", "NEXUS", "D", "HOME"):
        v = REPO if alias == "SKILLS" else roots.get(alias)
        root_status.append({"alias": alias, "path": v or "", "exists": bool(v and os.path.isdir(v))})

    data = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version": _read_version(),
        "machine_id": roots.get("machine_id", ""),
        "first_run": not roots.get("_setup_done", True),
        # 向导勾过、现在够不着的项目（外接盘拔了/网络盘断了/目录挪了）——要显示，不许静默
        "unreachable_projects": list(getattr(discover_projects, "unreachable", [])),
        # 被移出项目库的（文件都还在）。要列出来，否则「移错了怎么找回」无解
        "excluded_projects": [{"path": p, "exists": os.path.isdir(p)}
                              for p in roots.get("_excluded", [])],
        "root_status": root_status,
        "map_html": mdlite.render(map_text),
        "layers": layers,
        "sources": sources,
        "health": health,
        "projects": projects,
        "pitfall": {"sections": pit_sections, "columns": columns, "rows": pit_rows},
        "methods": methods,
        "evolution": evolution,
        "sync": sync,
    }
    if out_dir:
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        with io.open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    return data


def serve(open_browser):
    import http.server
    import socket
    import urllib.error
    import urllib.request

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=WEB, **kw)

        def end_headers(self):
            # 禁止浏览器缓存：界面升级后用户永远看到最新版
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def _json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/data.json":
                p = os.path.join(ACTIVE_SITE, "data.json")
                with io.open(p, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                super().do_GET()

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            except ValueError:
                self._json(400, {"ok": False, "error": "请求不是合法 JSON"})
                return
            routes = {
                "/api/templates": lambda: (200, api_templates()),
                "/api/create_project": lambda: api_create_project(data),
                "/api/run_generator": lambda: api_run_generator(data),
                "/api/apply_seed_update": lambda: api_apply_seed_update(data),
                "/api/project_detail": lambda: api_project_detail(data),
                "/api/open_dir": lambda: api_open_dir(data),
                "/api/install_organs": lambda: api_install_organs(data),
                "/api/add_pitfall": lambda: api_add_pitfall(data),
                "/api/audit_delete": lambda: api_audit_delete(data),
                "/api/sync_project": lambda: api_sync_project(data),
                "/api/refresh": lambda: api_refresh(data),
                "/api/project_add": lambda: api_project_add(data),
                "/api/project_remove": lambda: api_project_remove(data),
                "/api/project_restore": lambda: api_project_restore(data),
                "/api/setup_state": lambda: api_setup_state(data),
                "/api/browse": lambda: api_browse(data),
                "/api/pick_folder": lambda: api_pick_folder(data),
                "/api/find_projects": lambda: api_find_projects(data),
                "/api/setup_save": lambda: api_setup_save(data),
            }
            fn = routes.get(self.path)
            if fn:
                status, payload = fn()
                self._json(status, payload)
            else:
                self._json(404, {"ok": False, "error": "没有这个接口"})

        def log_message(self, *a):
            pass

    class ExclusiveHTTPServer(http.server.ThreadingHTTPServer):
        """独占绑定。

        HTTPServer 默认 allow_reuse_address=1。这在 Linux 只放行 TIME_WAIT，
        在 Windows 却允许直接抢占一个正在 LISTEN 的端口——于是下面的端口探测
        永远 break 在第一个端口、OSError 永不触发，每起一个新实例都会静默
        夺走老实例的端口，老页面的 fetch 落到哪个进程全看运气。
        SO_EXCLUSIVEADDRUSE 把这条路堵死：既不抢别人的，也不许别人抢自己的。
        """
        allow_reuse_address = False

        # stdlib 默认 request_queue_size=5，也就是 accept 队列只排得下 5 个。
        # ⛔ Windows 在这个队列满时**发 RST**（Linux 是丢 SYN 让客户端重试），
        #    客户端拿到的就是 ConnectionResetError(10054)——在浏览器里长成
        #    `TypeError: Failed to fetch`，和"产品挂了"一模一样。
        # 隔离实测（同 handler、200 请求 / 50 线程、跑 8 轮，只换这一个量）：
        #    队列 5   → 1588/1600，8 轮里 4 轮有失败，12 次 ConnectionResetError
        #    队列 128 → 1600/1600，0 轮失败
        # 这是 stress_b 那条并发用例间歇性红的真因——不是测试写松了，是真会丢请求。
        # 触发不需要压测：多开几个标签页 + AI 在轮询 + 手动刷新就够了。
        request_queue_size = 128

        def server_bind(self):
            if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

    def lingtai_already_on(port):
        """这个端口上跑着的是不是一个灵台实例（不是就让开，去下一个端口）"""
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/" % port, timeout=0.6) as r:
                return b"LingTai" in r.read(4096)
        except (urllib.error.URLError, OSError):
            return False

    srv = None
    for port in range(8765, 8771):
        # 已经有一个灵台在跑 → 把浏览器指过去，不再起第二个进程
        if lingtai_already_on(port):
            url = "http://127.0.0.1:%d/" % port
            print("灵台 LingTai OS 已在运行：%s  （不重复启动）" % url)
            if open_browser:
                webbrowser.open(url)
            return
        try:
            srv = ExclusiveHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            srv = None
    if srv is None:
        print("[XX] 8765-8770 端口全被别的程序占了")
        sys.exit(1)
    url = "http://127.0.0.1:%d/" % port
    print("灵台 LingTai OS 已起：%s  （Ctrl+C 停）" % url)
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停。")


def _sweep_stale_unpack():
    """清掉自己以前留下的解包垃圾（PyInstaller onefile 的 _MEIxxxx 临时目录）。

    单文件 exe 每次启动会把自己解压到临时目录，正常退出会清理——**但被强杀或崩溃时不会**。
    实测本机积压了 319 个、9.66 GB。用户那边同样会发生：任务管理器结束进程一次、
    崩一次，就留下约 30 MB，日积月累。

    ⛔ 只删「不是本次这个」且「超过一天没动过」的：正在被别的实例占用的目录删不掉，
       Windows 会抛异常，直接跳过——宁可留着也不能删掉别人正在用的。
    """
    if not BUNDLE:
        return
    try:
        import tempfile as _tf
        now, cut = time.time(), 24 * 3600
        mine = os.path.normcase(os.path.abspath(BUNDLE))
        for p in glob.glob(os.path.join(_tf.gettempdir(), "_MEI*")):
            if not os.path.isdir(p) or os.path.normcase(os.path.abspath(p)) == mine:
                continue
            try:
                if now - os.path.getmtime(p) < cut:
                    continue
                shutil.rmtree(p, ignore_errors=False)
            except OSError:
                pass          # 正被占用/没权限：跳过，不出声也不冒险
    except Exception:
        pass                  # 清垃圾失败绝不能影响启动


SEED_MANIFEST = os.path.join(REPO, ".seeded.json")


def _seed_state():
    try:
        with io.open(SEED_MANIFEST, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _seed_repo():
    """exe 启动：把出厂的方法论真源从只读的 BUNDLE 落到 exe 旁边（REPO = HERE）。

    落盘之后，坑库/装配图/常驻薄核等的读写都走这份持久副本——那是**用户的资产**，
    必须活过进程退出。以前 REPO 直接指 BUNDLE（临时解压目录），记进去的坑重启就没。

    ⛔ 绝不覆盖用户改过的内容。这条不给任何开关。

    以前的实现是「不存在才复制」，代价是**新版带的方法论更新永远不会生效**——
    升级传播机制一直空着（HANDOFF item 6）。而「不存在才复制」之所以必要，
    只是因为**分不清哪份是用户改的、哪份是我们上次写下去的**。
    那就把这件事记下来：`.seeded.json` 存「我们上次写给你的那份长什么样」。于是：

      · 磁盘上没有            → 复制，记账
      · 和我们上次写的一字不差 → 用户没动过，**安全升级**，更新记账
      · 和我们上次写的不一样   → 用户改过，**留着不动**，并说出来
      · 台账里根本没有         → v0.2.0 及更早装的，分不清，**留着不动**，
                                 挂到界面上让人自己决定要不要更新（覆盖前留 .bak）
    """
    if not BUNDLE:
        return
    state = _seed_state()
    known = dict(state.get("files") or {})
    landed, updated, kept, pending = 0, [], [], []
    for top in ("project-delivery", "agent-worksheet"):
        src_root = os.path.join(BUNDLE, top)
        if not os.path.isdir(src_root):
            continue
        for dirpath, _dirnames, filenames in os.walk(src_root):
            rel = os.path.relpath(dirpath, src_root)
            dst_dir = os.path.join(REPO, top) if rel == "." else os.path.join(REPO, top, rel)
            sub = "" if rel == "." else rel.replace("\\", "/") + "/"
            for fn in filenames:
                src, dst = os.path.join(dirpath, fn), os.path.join(dst_dir, fn)
                key = "%s/%s%s" % (top, sub, fn)
                try:
                    if not os.path.isfile(dst):
                        if not os.path.isdir(dst_dir):
                            os.makedirs(dst_dir)
                        shutil.copyfile(src, dst)
                        known[key] = _md5(dst)
                        landed += 1
                        continue
                    cur, new = _md5(dst), _md5(src)
                    if cur == new:
                        known[key] = cur          # 已经是这一版，登记为「我们的」
                        continue
                    prev = known.get(key)
                    if prev is not None and prev == cur:
                        shutil.copyfile(src, dst)  # 我们上次写的，用户一字没动
                        known[key] = new
                        updated.append(key)
                    elif prev is not None:
                        kept.append(key)           # 用户改过，绝不覆盖
                    else:
                        pending.append(key)        # 老装机没台账，分不清，等人裁决
                except OSError as e:
                    # 兜底必须出声：落不下去就等于又回到「记了会丢」，不许静默
                    print("[!!] 出厂真源落盘失败 %s：%s" % (fn, e))
    try:
        with io.open(SEED_MANIFEST, "w", encoding="utf-8") as f:
            json.dump({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "version": _read_version(),
                       "files": known, "kept": kept, "pending": pending},
                      f, ensure_ascii=False, indent=2)
    except OSError as e:
        print("[!!] 写不了升级台账 %s：%s（下次启动会当成老装机处理）" % (SEED_MANIFEST, e))
    if landed:
        print("[首跑] 已把 %d 个出厂方法论文件落到 %s" % (landed, REPO))
        print("       以后你在这里改的、记的，都归你——升级 exe 不会覆盖它们。")
    if updated:
        print("[升级] %d 个你没改过的方法论文件已更新到新版：%s" % (len(updated), "、".join(updated[:5])))
    if kept:
        print("[保留] %d 个你改过的文件没被覆盖（新版内容不同）：%s" % (len(kept), "、".join(kept[:5])))
    if pending:
        print("[待定] %d 个文件是更早版本装的、认不出来历，没动：%s" % (len(pending), "、".join(pending[:5])))
        print("       要不要换成新版，去 设置 → 整理 → 🔧 体系自检 里决定（覆盖前会留 .bak）")


def main():
    ap = argparse.ArgumentParser(description="大脑驾驶舱")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--health", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--roots-file", help="覆盖 roots.json 落点（演练/多机配置）")
    ap.add_argument("--regen", metavar="项目或brain目录",
                    help="重算这个项目的 02_状态（不需要装 Python，exe 自己就能跑生成器）")
    args = ap.parse_args()

    # frozen 首跑：落示例文件 + 自动探测各根写 roots.json（否则 load_roots 直接退出，界面打不开）
    if _FROZEN:
        for f in ("AI开窗必读.md", "roots.example.json"):
            src = os.path.join(BUNDLE, f)
            dst = os.path.join(HERE, f)
            if os.path.isfile(src) and not os.path.isfile(dst):
                try:
                    shutil.copyfile(src, dst)
                except OSError:
                    pass
        _seed_repo()
        _sweep_stale_unpack()
        if not os.path.isfile(ROOTS_FILE):
            home = os.path.expanduser("~")
            roots = {
                "NEXUS": "C:\\nexus_local" if os.path.isdir("C:\\nexus_local") else None,
                "D": "D:\\" if os.path.isdir("D:\\") else None,
                "HOME": home,
            }
            machine_id = os.environ.get("COMPUTERNAME") or "unknown"
            # setup_done=false → 前端进首跑向导，让用户确认/改扫描位置、挑自己的项目。
            # 仍然先写一份自动探测结果：服务照常起得来，向导只是「确认并调整」，
            # 不是「从零配置」——启动路径一行没动，零风险。
            # 老的 roots.json 没有这个字段，load_roots 缺省当 true，不打扰现有用户。
            with io.open(ROOTS_FILE, "w", encoding="utf-8") as f:
                json.dump({"machine_id": machine_id, "roots": roots, "setup_done": False},
                          f, ensure_ascii=False, indent=2)

    # ⛔ 这个入口不是锦上添花，是补一个断掉的闭环。
    #    「继续做」指令让 AI 收工时跑 `python -X utf8 状态生成器.py`，
    #    而本文件的 _run_generator 里白纸黑字写着「用户机器上可能根本没有 Python」——
    #    产品为了零依赖亲手绕开的东西，却写进了发给用户的说明书。
    #    下载 exe 的人手上一定有 exe，不一定有 python.exe。所以给 exe 一条等价命令。
    #    放在 _seed_repo() 之后：生成器真源是首跑落盘的，早于它跑就找不到。
    if args.regen:
        brain = os.path.abspath(args.regen)
        # 给项目根目录也认——少一次「路径给错了」的往返
        if os.path.basename(brain).lower() != "brain" and os.path.isdir(os.path.join(brain, "brain")):
            brain = os.path.join(brain, "brain")
        if not os.path.isdir(brain):
            print("[XX] 不是一个目录：%s" % brain)
            sys.exit(2)
        g = _run_generator(brain)
        if g.get("error"):
            print("[XX] 重算失败：%s" % g["error"])
            sys.exit(1)
        tail = (g.get("out") or "").strip()
        if tail:
            print(tail[-1200:])
        if g.get("exit"):
            print("[XX] 生成器退出码 %s%s" % (g["exit"], ("：" + g["err"]) if g.get("err") else ""))
            sys.exit(1)
        print("[OK] 已重算 %s" % brain)
        sys.exit(0)

    if args.roots_file:
        global ACTIVE_ROOTS_FILE, ACTIVE_SITE
        ACTIVE_ROOTS_FILE = os.path.abspath(args.roots_file)
        # 演练的产物也落在演练目录里，别写回真 site/
        ACTIVE_SITE = os.path.join(os.path.dirname(ACTIVE_ROOTS_FILE), "site")
    roots = load_roots()

    if args.selftest:
        print("dashboard · 破坏性自检")
        # 进程内调用（frozen 模式下无外部 python/vendor 目录，mdlite 已随包导入）
        if not mdlite._selftest():
            sys.exit(1)
        data = build(roots, None)
        ok = True

        def ck(c, m, detail=""):
            # 失败必须说出为什么。只打一个 ✗ 的自检 = 兜底不出声：
            # exe 里「生成器跑不起来」曾只显示 ✗，真因（ModuleNotFoundError: glob）
            # 要另外起服务打 API 才挖得出来。
            nonlocal ok
            line = ("  ok " if c else "  ✗ ") + m
            if not c and detail:
                line += "  ← " + str(detail).strip().replace("\n", " ")[:300]
            print(line)
            ok = ok and c

        ck(len(data["layers"]) >= 7, "七层表解析 ≥7 行（实 %d）" % len(data["layers"]))
        ck(len(data["sources"]) >= 50, "逐文件清单解析 ≥50 条（实 %d）" % len(data["sources"]))
        ck(len(data["pitfall"]["rows"]) >= 30, "坑库解析 ≥30 条（实 %d）" % len(data["pitfall"]["rows"]))
        ck(len(data["projects"]) >= 3, "项目自动发现 ≥3（实 %d）" % len(data["projects"]))
        # 判据强度分档：喂已知的三种坏写法，它必须都判出来——只验「有 grade_stats 字段」
        # 等于没验（那是 P8：读数是 0 和读数只能是 0 长得一样）。
        _gs = data["evolution"].get("grade_stats") or {}
        _cases = [
            ("以后注意别再这样", "改完回读", "弱"),                     # 空话
            ("改完必 Read 回读；跨机走 md5", "改完必 Read 回读；跨机走 md5", "弱"),  # 循环：与防法同文
            ("写操作封装强制回读校验，代码中不存在裸写接口", "改完回读", "强"),      # 说清谁来验
            ("待补", "随便", "缺"),
        ]
        _bad = [c for c, f, want in _cases if grade_criterion(c, f)[0] != want]
        ck(not _bad, "判据强度分档认得出空话/循环/结构性（统计：%s）"
           % "/".join("%s%d" % (k, _gs.get(k, 0)) for k in ("强", "中", "弱", "缺")),
           "判错：%s" % _bad)
        ck(len(data["methods"]) == 4 and all(m["ok"] for m in data["methods"]),
           "方法论四篇都在位", "缺：%s" % [m["name"] for m in data["methods"] if not m["ok"]])
        ck(any("{NEXUS}/00_core/装配图.md" in s["path"] for s in data["sources"]), "00_core 装配图指针已登记")
        t = api_templates()
        ck(t["ok"] and "AI开窗必读" in t["open"] and os.path.isfile(t["paths"]["card"]),
           "开窗指令模板含真实路径")
        st, payload = api_create_project({"name": "../evil", "root_choice": "nexus"})
        ck(st == 400, "项目名非法被拒（../evil → %s）" % st)
        sandbox_path = os.path.join(roots.get("NEXUS") or "", "sandbox")
        st, payload = api_create_project({"name": "x", "root_choice": "custom", "custom_path": sandbox_path})
        ck(st == 403, "sandbox 只读红线被拒（403）")
        # 一键装系统机制：临时假历史项目 → 装成功 → 二次装拒绝（不经 API，不污染装配图）
        import tempfile
        tmp = tempfile.mkdtemp(prefix="bc_organs_")
        try:
            brain = _install_organs_files(tmp, "tmp-proj", retro=True)
            gen = _run_generator(brain)
            ck(gen.get("exit") == 0 and os.path.isfile(os.path.join(brain, "02_状态.json")),
               "一键装系统装出六器官+状态",
               gen.get("error") or gen.get("err") or gen.get("out", "")[-200:])
            try:
                _install_organs_files(tmp, "tmp-proj")
                ck(False, "重复装系统被拒")
            except OSError:
                ck(True, "重复装系统被拒（brain 已存在）")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        # 生成器 --dir 共享直跑（v0.7）
        tmp2 = tempfile.mkdtemp(prefix="bc_dir_")
        try:
            with io.open(os.path.join(tmp2, "状态源.json"), "w", encoding="utf-8") as f:
                json.dump({"project": "T", "root": ".", "probes": [
                    {"name": "n", "type": "file_count", "glob": "*"}]}, f)
            g = _run_generator(tmp2)
            ck(g.get("exit") == 0 and os.path.isfile(os.path.join(tmp2, "02_状态.json")),
               "生成器 --dir 从 skills 真源直跑（v0.7 共享化）",
               g.get("error") or g.get("err") or g.get("out", "")[-200:])
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)
        # 进坑向导：缺失效判据 400；录一条→删一条（真源往返，终态不变）
        st, _ = api_add_pitfall({"section": "工具坑", "pit": "x", "fix": "y", "invalid_when": ""})
        ck(st == 400, "缺失效判据不放行（400）")
        st, payload = api_add_pitfall({"section": "工具坑", "pit": "selftest 临时坑", "fix": "跑 selftest",
                                       "source": "selftest", "invalid_when": "selftest 结束即删"})
        ck(st == 200, "进坑向导录一条（200）")
        if st == 200:
            st2, d2 = api_audit_delete({"kind": "pitfall", "ids": [payload["code"]]})
            ck(st2 == 200 and d2.get("removed") == 1, "审计删除真源行消失")
        sys.exit(0 if ok else 1)

    data = build(roots, ACTIVE_SITE)
    h = data["health"]
    print("生成于 %s · 登记 %d 源（ok %d / missing %d / 无根 %d）· 项目 %d · 坑库 %d 条"
          % (data["generated_at"], h["total"], h["ok"], len(h["missing"]), h["noroot"],
             len(data["projects"]), len(data["pitfall"]["rows"])))

    if args.health:
        for m in h["missing"]:
            print("  [XX] %s → %s" % (m["path"], m["resolved"]))
        for pair in h["identical_pairs"]:
            print("  [!!] 同名同内容双份：%s <-> %s" % (pair["a"], pair["b"]))
        for p in h["noroot_paths"]:
            print("  [--] 本机无此根：%s" % p)
        sys.exit(0 if not h["missing"] and not h["identical_pairs"] else 1)

    if args.build_only:
        sys.exit(0)

    serve(not args.no_browser)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        if _FROZEN:
            import traceback
            traceback.print_exc()
            try:
                input("\n[出错] 按回车退出…")
            except (EOFError, KeyboardInterrupt):
                pass
            sys.exit(1)
        raise
