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
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import mdlite  # noqa: E402

# PyInstaller onefile 适配：exe 所在目录 = 用户数据（roots.json/site/）；解包目录 = 只读资产（web/方法真源）
_FROZEN = getattr(sys, "frozen", False)
if _FROZEN and os.name == "nt":
    # exe 控制台走 GBK（中文 Windows 默认代码页），否则中文消息乱码
    try:
        sys.stdout.reconfigure(encoding="gbk", errors="replace")
        sys.stderr.reconfigure(encoding="gbk", errors="replace")
    except (AttributeError, OSError):
        pass
if _FROZEN:
    HERE = os.path.dirname(os.path.abspath(sys.executable))
    BUNDLE = sys._MEIPASS  # noqa
    REPO = BUNDLE
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
    BUNDLE = None
    REPO = os.path.dirname(HERE)
MAP = os.path.join(REPO, "project-delivery", "装配图.md")
PITFALL = os.path.join(REPO, "project-delivery", "坑库.md")
SITE = os.path.join(HERE, "site")
WEB = os.path.join(BUNDLE, "web") if BUNDLE else os.path.join(HERE, "web")
ROOTS_FILE = os.path.join(HERE, "roots.json")
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
    p = path or ROOTS_FILE
    if not os.path.isfile(p):
        print("[XX] 缺 roots.json（%s）—— 先跑：python -X utf8 install.py" % p)
        sys.exit(2)
    with io.open(p, encoding="utf-8") as f:
        d = json.load(f)
    r = dict(d.get("roots", {}))
    r["machine_id"] = d.get("machine_id", "")
    return r


# ── 向导 API（v0.2 · 傻瓜式：点按钮，不背规则）─────────────────────

PROJECT_NAME_RE = re.compile(r"^[\w一-龥\- ]+$")
SCAFFOLD_FILES = ["00_宪法.md", "01_法典.md", "03_在建.md", "04_待办池.md",
                  "05_交接.md", "06_提案层.md", "关口清单.md", "规则台账.md", "状态生成器.py"]


def api_templates():
    card = os.path.join(HERE, "AI开窗必读.md")
    open_text = (
        "1. 先读 %s（AI开窗必读，照做开窗五步）\n"
        "2. 读本项目 brain\\01_法典.md 和 brain\\05_交接.md，告诉我：现在到哪了、下一步是什么\n"
        "3. 每完成一个完整任务段，立刻把「做到哪 / 下一步」更新进 brain\\05_交接.md"
        "（不要等收窗；我随时会离开，进度必须在文件里）\n"
        "4. 每段回复第一行打证据头；不可逆动作先出施工图等我拍板"
    ) % card
    close_text = (
        "按收窗四步收：①销账（回状态源标死已完成项）②教训进坑库/法典（不记流水账）"
        "③C 类过程标到期 ④更新 brain\\05_交接.md\n"
        "收完跑 python -X utf8 状态生成器.py 并报告告警"
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
    choice = data.get("root_choice", "nexus")
    if choice == "nexus":
        base = roots.get("NEXUS")
    elif choice == "d":
        base = roots.get("D")
    elif choice == "custom":
        base = (data.get("custom_path") or "").strip()
        if not base or not os.path.isdir(base):
            return 400, {"ok": False, "error": "自定义路径不存在"}
    else:
        return 400, {"ok": False, "error": "root_choice 不合法"}
    if not base:
        return 400, {"ok": False, "error": "所选根未配置（先跑 install.py）"}
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
    # 重建 data.json，项目页立即可见
    try:
        build(load_roots(), SITE)
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
        build(load_roots(), SITE)
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
    new_row = "| %s | %s | %s | %s | 1 | %s | %s |" % (
        code, pit.replace("|", "/"), fix.replace("|", "/"), source.replace("|", "/"),
        invalid_when.replace("|", "/"), time.strftime("%Y-%m-%d"))
    lines = text.split("\n")
    sec_idx = next(i for i, ln in enumerate(lines) if ln.startswith("## %s" % section))
    nxt = next((i for i in range(sec_idx + 1, len(lines))
                if lines[i].startswith("## ")), len(lines))
    insert_at = max(i for i in range(sec_idx, nxt) if lines[i].startswith("| "))
    lines.insert(insert_at + 1, new_row)
    with io.open(PITFALL, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    try:
        build(load_roots(), SITE)
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
            build(load_roots(), SITE)
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
            build(load_roots(), SITE)
        except Exception:
            pass
        return 200, {"ok": True, "removed": removed}
    return 400, {"ok": False, "error": "kind 不合法"}


def evolution_data(projects, pit_rows, health):
    """进化审计五清单：待补判据 / 候选删除 / C类到期 / 交接过期 / 断头双份。"""
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
    new_this_week = sum(1 for r in pit_rows if (r.get("入库") or "") >= week_ago)
    return {
        "missing_invalid": missing_invalid,
        "candidates": candidates,
        "expired_todos": expired_todos,
        "stale_handoffs": stale_handoffs,
        "broken": health["missing"],
        "identical_pairs": health["identical_pairs"],
        "new_this_week": new_this_week,
        "total_pitfalls": len(pit_rows),
    }


def _register_in_map(section_marker, new_row):
    """在装配图指定小节末表格追加一行（真源登记，先改图）。"""
    with io.open(MAP, encoding="utf-8") as f:
        lines = f.read().split("\n")
    sec_idx = next((i for i, ln in enumerate(lines) if ln.startswith(section_marker)), None)
    if sec_idx is None:
        return
    nxt = next((i for i in range(sec_idx + 1, len(lines))
                if lines[i].startswith("### ") or lines[i].startswith("## ")), len(lines))
    insert_at = max(i for i in range(sec_idx, nxt) if lines[i].startswith("|"))
    if new_row not in lines:
        lines.insert(insert_at + 1, new_row)
        with io.open(MAP, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


def _run_generator(brain_dir):
    """用 skills 真源直跑任意项目（v0.7 共享化：--dir，项目副本只是快照）。"""
    gen = os.path.join(REPO, "project-delivery", "scaffold", "状态生成器.py")
    if not os.path.isfile(gen):
        return {"error": "生成器真源不在：%s" % gen}
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", gen, "--dir", brain_dir],
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
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
        d = build(load_roots(), SITE)
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
        build(load_roots(), SITE)
    except Exception:
        pass
    return 200, {"ok": True, "synced": n}


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
    hand_p = os.path.join(brain, "05_交接.md")
    if os.path.isfile(hand_p):
        t = _read_md(hand_p) or ""
        m = re.search(r"## 本窗做完的 / 没做完的(.*?)(?=\n## |\Z)", t, re.S)
        if m:
            detail["handoff_done"] = mdlite.render(m.group(1))

    # 根级 md 只列名不渲染（旧项目文档内容不可预知，守"涉密不渲染"红线）
    try:
        detail["root_md"] = sorted(e for e in os.listdir(path)
                                   if e.lower().endswith(".md") and os.path.isfile(os.path.join(path, e)))
    except OSError:
        detail["root_md"] = []

    # 告警
    alarms = []
    sj = os.path.join(brain, "02_状态.json")
    if os.path.isfile(sj):
        try:
            with io.open(sj, encoding="utf-8") as f:
                alarms = json.load(f).get("alarms", [])
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
        close_step = ("更新 %s（做完的/没做完的），然后跑 python -X utf8 状态生成器.py（在 %s 目录）——"
                      "下次双击驾驶舱，进度自动反映") % (hand_p, brain)
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
    steps.append("4. 每段回复第一行打证据头；不可逆动作先出施工图等我拍板" if trace_step is None else
                 "5. 每段回复第一行打证据头；不可逆动作先出施工图等我拍板")
    steps.append(("5. 收工时：%s" if trace_step is None else "6. 收工时：%s") % close_step)
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
                    resolved = resolve(raw, roots)
                    sources.append({
                        "layer": layer,
                        "path": raw,
                        "resolved": resolved or "",
                        "nature": d.get("性质", ""),
                        "note": d.get("备注", ""),
                        "status": "noroot" if resolved is None else _status(resolved),
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
        "missing": [{"layer": s["layer"], "path": s["path"], "resolved": s["resolved"]} for s in missing],
        "noroot": len(noroot), "noroot_paths": [s["path"] for s in noroot],
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

    def scan(base):
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
            if os.path.isdir(p) and has_md(p):
                found[os.path.normpath(p).lower()] = p

    scan(os.path.join(roots.get("NEXUS"), "sandbox") if roots.get("NEXUS") else None)
    # D 盘项目 = 装配图 L6 登记的 {D}/ 行（单一权威源：图说谁是项目，谁就是）
    for s in sources:
        if s["layer"] == "L6" and s["path"].startswith("{D}/"):
            p = (s["resolved"] or "").rstrip("\\/")
            if os.path.isdir(p):
                found[os.path.normpath(p).lower()] = p
    found[os.path.normpath(HERE).lower()] = HERE  # 驾驶舱自己

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
        handoff = os.path.join(p, "HANDOFF.md")
        projects.append({
            "name": os.path.basename(p),
            "path": p,
            "organs": organs,
            "alarms": alarms,
            "state": state,
            "state_at": at,
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

    methods = []
    for name, path in METHOD_DOCS:
        with io.open(path, encoding="utf-8") as f:
            methods.append({"name": name, "path": path, "html": mdlite.render(f.read())})

    evolution = evolution_data(projects, pit_rows, health)
    sync = sync_probe(projects)

    root_status = []
    for alias in ("SKILLS", "NEXUS", "D", "HOME"):
        v = REPO if alias == "SKILLS" else roots.get(alias)
        root_status.append({"alias": alias, "path": v or "", "exists": bool(v and os.path.isdir(v))})

    data = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "machine_id": roots.get("machine_id", ""),
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
                p = os.path.join(SITE, "data.json")
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
                "/api/project_detail": lambda: api_project_detail(data),
                "/api/open_dir": lambda: api_open_dir(data),
                "/api/install_organs": lambda: api_install_organs(data),
                "/api/add_pitfall": lambda: api_add_pitfall(data),
                "/api/audit_delete": lambda: api_audit_delete(data),
                "/api/sync_project": lambda: api_sync_project(data),
                "/api/refresh": lambda: api_refresh(data),
            }
            fn = routes.get(self.path)
            if fn:
                status, payload = fn()
                self._json(status, payload)
            else:
                self._json(404, {"ok": False, "error": "没有这个接口"})

        def log_message(self, *a):
            pass

    for port in range(8765, 8771):
        try:
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            srv = None
    if srv is None:
        print("[XX] 8765-8770 端口全被占")
        sys.exit(1)
    url = "http://127.0.0.1:%d/" % port
    print("灵台 LingTai OS 已起：%s  （Ctrl+C 停）" % url)
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停。")


def main():
    ap = argparse.ArgumentParser(description="大脑驾驶舱")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--health", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--roots-file", help="覆盖 roots.json 落点（演练/多机配置）")
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
        if not os.path.isfile(ROOTS_FILE):
            home = os.path.expanduser("~")
            roots = {
                "NEXUS": "C:\\nexus_local" if os.path.isdir("C:\\nexus_local") else None,
                "D": "D:\\" if os.path.isdir("D:\\") else None,
                "HOME": home,
            }
            machine_id = os.environ.get("COMPUTERNAME") or "unknown"
            with io.open(ROOTS_FILE, "w", encoding="utf-8") as f:
                json.dump({"machine_id": machine_id, "roots": roots}, f, ensure_ascii=False, indent=2)

    roots = load_roots(args.roots_file)

    if args.selftest:
        print("dashboard · 破坏性自检")
        # 进程内调用（frozen 模式下无外部 python/vendor 目录，mdlite 已随包导入）
        if not mdlite._selftest():
            sys.exit(1)
        data = build(roots, None)
        ok = True

        def ck(c, m):
            nonlocal ok
            print(("  ok " if c else "  ✗ ") + m)
            ok = ok and c

        ck(len(data["layers"]) >= 7, "七层表解析 ≥7 行（实 %d）" % len(data["layers"]))
        ck(len(data["sources"]) >= 50, "逐文件清单解析 ≥50 条（实 %d）" % len(data["sources"]))
        ck(len(data["pitfall"]["rows"]) >= 30, "坑库解析 ≥30 条（实 %d）" % len(data["pitfall"]["rows"]))
        ck(len(data["projects"]) >= 3, "项目自动发现 ≥3（实 %d）" % len(data["projects"]))
        ck(len(data["methods"]) == 4, "四真源渲染齐")
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
               "一键装系统装出六器官+状态")
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
               "生成器 --dir 从 skills 真源直跑（v0.7 共享化）")
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

    data = build(roots, SITE)
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
