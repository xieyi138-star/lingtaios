# -*- coding: utf-8 -*-
"""大脑驾驶舱 · 装机脚本（stdlib only，换电脑第一条命令）

用法:
    python -X utf8 install.py                          # 自动探测，探测不到再问
    python -X utf8 install.py --nexus C:\\nexus_local --d D:\\ --home C:\\Users\\X   # 非交互
    python -X utf8 install.py --claude-dir <path>      # 覆盖 ~/.claude 落点（演练/特殊环境）
    python -X utf8 install.py --check                  # 只自检不写任何东西

行为:
    1. 探测 python（>=3.8）与仓库根（自动认两种布局：主源码 skills\\brain-console\\ 下，
       或发布仓摊平后 install.py 与 project-delivery/ 同级）
    2. 自动探测机器根：NEXUS（存在 C:\\nexus_local 即用）、D（存在 D:\\ 即用）、HOME（用户主目录）
    3. 写 roots.json（machine_id + 各根）；roots.json 不随仓（gitignore）
    4. 写/补 ~/.claude/CLAUDE.md 启动器指针（存在则追加装配图行，不覆盖任何内容）
    5. 自检：方法层真源逐一 Test-Path，输出红绿表
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# ⛔ 两种布局都要认，和 lingtaios.spec / tests/soul_manifest.py 用同一个判据：
#     主源码  skills\brain-console\install.py → 方法层真源在**上一级**，驾驶舱在 brain-console\
#     发布仓  repo\install.py                 → 发布时摊平，方法层真源和驾驶舱都在**同级**
# 这里曾经无条件 dirname(dirname(__file__))，于是从公开仓 clone 下来跑
# 「换电脑第一条命令」，12 项方法层真源全报 [XX]、退出码 1——文件明明都在，
# 只是往上多找了一层。用户看到的是满屏红叉，等于系统装不上。实测复现过。
_FLAT = os.path.isdir(os.path.join(HERE, "project-delivery"))
REPO = HERE if _FLAT else os.path.dirname(HERE)
BC = HERE if _FLAT else os.path.join(REPO, "brain-console")

# 方法层真源（与 装配图.md §4 L1/L2 一致，装机自检用；改装配图时同步这里）
METHOD_SOURCES = [
    "project-delivery/常驻薄核.md",
    "project-delivery/SKILL.md",
    "project-delivery/项目交付法.md",
    "project-delivery/核心大脑.md",
    "project-delivery/道法术.md",
    "project-delivery/坑库.md",
    "project-delivery/装配图.md",
    "project-delivery/scaffold/README.md",
    "project-delivery/scaffold/状态生成器.py",
    "project-delivery/scaffold/状态源.示例.json",
    "agent-worksheet/SKILL.md",
    # L0 强制层（装配图 §4 L0）。缺了它整套规则退回「全靠自觉」，
    # 而那个状态和装好了从外面看一模一样——所以它必须进自检表。
    "project-delivery/hooks/config.json",
    "project-delivery/hooks/gate.ps1",
    "project-delivery/hooks/gate.sh",
    "project-delivery/hooks/pit_gate_map.json",
    "project-delivery/hooks/README.md",
]

# L0 挂到 Claude Code 的哪些事件上。matcher 只在 PreToolUse 有意义。
# ⛔ 不写 "*"：那等于每次工具调用都启一个 PowerShell（约 200-300ms），
#    而读文件/搜索这类高频只读操作根本不需要进闸。
L0_EVENTS = [
    ("SessionStart", None),
    ("Stop", None),
    ("PreToolUse", "Write|Edit|NotebookEdit|Bash|PowerShell"),
]

LAUNCHER_LINES = [
    "---",
    "",
    "## 本机环境（只写会影响每个动作的，不写项目内容）",
    "",
    "- PowerShell 命令行**不要写中文**（会被吃掉 / 卡续行符）；`>` 重定向是 UTF-16LE",
    "- 写 Windows 路径的文件用 Filesystem/DC 的 write_file，**不要用 create_file**（写进容器沙箱，Windows 侧找不到）",
    "- 项目专属的地图 / 路由 / 阶段目标 / 红线 → 看该项目根目录的 `CLAUDE.md`",
    "- 定位任何知识 / 文件 / 真源 → 读 `~/.claude/skills/project-delivery/装配图.md`（唯一导航真源，只登记不复制）",
    "",
]


def detect_root(candidate):
    if candidate and os.path.isdir(candidate):
        return candidate
    return None


def _l0_handler():
    """本平台跑 L0 闸门的命令。Windows 走 gate.ps1，其余走 gate.sh。"""
    if os.name == "nt":
        return {
            "type": "command",
            "command": "powershell.exe",
            "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                     os.path.join(REPO, "project-delivery", "hooks", "gate.ps1")],
            "timeout": 20,
        }
    return {
        "type": "command",
        "command": "bash",
        "args": [os.path.join(REPO, "project-delivery", "hooks", "gate.sh")],
        "timeout": 20,
    }


def _gate_path_of(handler):
    a = handler.get("args") or []
    return a[-1] if a else ""


def l0_status(claude_dir):
    """(已挂载?, 说明)。只读，不写。"""
    p = os.path.join(claude_dir, "settings.json")
    if not os.path.isfile(p):
        return (False, "settings.json 不存在")
    try:
        with open(p, encoding="utf-8-sig") as f:
            conf = json.load(f)
    except (OSError, ValueError) as e:
        # ⛔ 这一档必须和「没装」分开：settings.json 语法坏了的时候，
        #    Claude Code 会连 permissions 一起失效，而那看起来像别的毛病。
        return (False, "settings.json 读不出来（%s）——先修它，别急着装 L0" % e.__class__.__name__)
    want = os.path.normcase(_gate_path_of(_l0_handler()))
    for ev, _m in L0_EVENTS:
        entries = conf.get("hooks", {}).get(ev) or []
        found = False
        for grp in entries:
            for h in (grp.get("hooks") or []):
                if os.path.normcase(_gate_path_of(h)) == want:
                    found = True
        if not found:
            return (False, "缺 %s 这一挂" % ev)
    return (True, "三个事件都挂着")


def install_l0(claude_dir):
    """把 L0 挂进 settings.json。**只增不覆盖**——这是用户自己的文件。

    ⛔ 已有的 hooks 一条都不动，只往对应事件的数组里追加自己那条；
       已经挂过就什么都不做（幂等）。
    ⛔ 写之前先备份，且走「先写临时文件再替换」（坑库 T15：
       open(...,'w') 是先截断后写，中途失败原文件就没了）。
    """
    p = os.path.join(claude_dir, "settings.json")
    conf = {}
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8-sig") as f:
                conf = json.load(f)
        except (OSError, ValueError) as e:
            print("[!!] settings.json 存在但读不出来（%s）——L0 没装。" % e.__class__.__name__)
            print("     不动它是故意的：这个文件里还有你的权限配置，"
                  "覆盖掉比不装 L0 贵得多。修好语法再跑一次。")
            return False
        bak = p + ".before-l0"
        if not os.path.isfile(bak):
            with open(bak, "w", encoding="utf-8") as f:
                json.dump(conf, f, ensure_ascii=False, indent=2)
            print("[OK] 原 settings.json 已备份：%s" % bak)

    handler = _l0_handler()
    if not os.path.isfile(_gate_path_of(handler)):
        print("[XX] 找不到闸门脚本：%s" % _gate_path_of(handler))
        return False

    hooks = conf.setdefault("hooks", {})
    want = os.path.normcase(_gate_path_of(handler))
    added = []
    for ev, matcher in L0_EVENTS:
        arr = hooks.setdefault(ev, [])
        already = any(os.path.normcase(_gate_path_of(h)) == want
                      for grp in arr for h in (grp.get("hooks") or []))
        if already:
            continue
        grp = {"hooks": [dict(handler)]}
        if matcher:
            grp["matcher"] = matcher
        arr.append(grp)
        added.append(ev)

    if not added:
        print("[OK] L0 已经挂着，未改动 settings.json")
        return True

    tmp = p + ".tmp"
    if not os.path.isdir(claude_dir):
        os.makedirs(claude_dir)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(conf, f, ensure_ascii=False, indent=2)
    # 先验新文件读得回来，再替换旧的（准备→验证→切换）
    with open(tmp, encoding="utf-8") as f:
        json.load(f)
    os.replace(tmp, p)
    print("[OK] L0 已挂上：%s（新增 %s）" % (p, ", ".join(added)))
    print("     关掉它：改 project-delivery/hooks/config.json 的 master_switch 为 false")
    print("     ⚠️ 需要重开一个 Claude Code 会话才生效")
    return True


def check(claude_dir, roots, out):
    """自检：方法层真源 + 启动器 + roots 有效性。写或不写都由 out 控制。"""
    lines = []
    w = lines.append
    ok = True
    w("=== 自检：方法层真源 ===")
    for rel in METHOD_SOURCES:
        p = os.path.join(REPO, rel)
        exists = os.path.isfile(p)
        ok = ok and exists
        w(("  [OK] " if exists else "  [XX] ") + rel)
    # 驾驶舱本体跟着布局走，不能写死 brain-console/ 这一层
    dash = os.path.join(BC, "dashboard.py")
    ok = ok and os.path.isfile(dash)
    w(("  [OK] " if os.path.isfile(dash) else "  [XX] ") + dash)
    w("=== 自检：机器根（装配图别名） ===")
    for name, path in sorted(roots.items()):
        if path is None:
            w("  [--] %s = 未配置（该层页面将显示「本机无此根」）" % name)
        elif os.path.isdir(path):
            w("  [OK] %s = %s" % (name, path))
        else:
            w("  [!!] %s = %s 路径不存在" % (name, path))
            ok = False
    w("=== 自检：启动器 %s ===" % os.path.join(claude_dir, "CLAUDE.md"))
    launcher = os.path.join(claude_dir, "CLAUDE.md")
    if os.path.isfile(launcher):
        with open(launcher, encoding="utf-8") as f:
            content = f.read()
        if "装配图.md" in content:
            w("  [OK] 启动器存在且已含装配图指针")
        else:
            w("  [!!] 启动器存在但缺装配图指针（install 会补）")
            ok = False
    else:
        w("  [!!] 启动器不存在（install 会创建）")
        ok = False
    # L0：装没装是能查的，不许靠「我记得装过」
    w("=== 自检：L0 强制层挂载 ===")
    mounted, why = l0_status(claude_dir)
    if mounted:
        w("  [OK] L0 已挂载（%s）" % why)
    else:
        w("  [!!] L0 未挂载：%s" % why)
        w("       没挂 = 整套规则退回全靠模型自觉，而这和装好了从外面看一模一样")
        ok = False
    print("\n".join(lines))
    return ok


def main():
    ap = argparse.ArgumentParser(description="大脑驾驶舱装机")
    ap.add_argument("--nexus", help="Nexus 业务根路径（无则 null）")
    ap.add_argument("--d", dest="ddrive", help="D 盘根路径（无则 null）")
    ap.add_argument("--home", help="用户主目录（默认探测）")
    ap.add_argument("--claude-dir", help="覆盖 ~/.claude 落点（演练用）")
    ap.add_argument("--roots-file", help="覆盖 roots.json 落点（演练用，默认仓库内）")
    ap.add_argument("--machine-id", help="machine_id（默认机器名）")
    ap.add_argument("--check", action="store_true", help="只自检不写")
    ap.add_argument("--no-hooks", action="store_true",
                    help="不挂 L0 强制层（默认会挂；挂上后规则由外部进程拦，不再靠模型自觉）")
    args = ap.parse_args()

    if sys.version_info < (3, 8):
        print("[XX] 需要 Python >= 3.8，当前 %s" % sys.version.split()[0])
        sys.exit(1)

    def _arg_or(value, default):
        """显式传空串 = 明确无此根（跳过自动探测）；不传 = 自动探测。"""
        if value == "":
            return None
        return value if value is not None else default

    home = args.home or os.path.expanduser("~")
    claude_dir = args.claude_dir or os.path.join(home, ".claude")
    machine_id = args.machine_id or os.environ.get("COMPUTERNAME") or "unknown-machine"
    roots = {
        "NEXUS": _arg_or(args.nexus, detect_root("C:\\nexus_local")),
        "D": _arg_or(args.ddrive, detect_root("D:\\")),
        "HOME": home,
    }

    if args.check:
        sys.exit(0 if check(claude_dir, roots, None) else 1)

    roots_path = args.roots_file or os.path.join(BC, "roots.json")
    with open(roots_path, "w", encoding="utf-8") as f:
        json.dump({"machine_id": machine_id, "roots": roots}, f, ensure_ascii=False, indent=2)
    print("[OK] roots.json 已写：%s" % roots_path)

    launcher = os.path.join(claude_dir, "CLAUDE.md")
    if not os.path.isdir(claude_dir):
        os.makedirs(claude_dir)
    if os.path.isfile(launcher):
        with open(launcher, encoding="utf-8") as f:
            content = f.read()
        if "装配图.md" not in content:
            with open(launcher, "a", encoding="utf-8") as f:
                f.write("\n" + LAUNCHER_LINES[-1] + "\n")
            print("[OK] 启动器已追加装配图指针行")
        else:
            print("[OK] 启动器已含装配图指针，未改动")
    else:
        body = (
            "# 用户级指令（跨所有项目）\n\n"
            "> 本文件是**启动器**，只指向真源，不复制内容。\n"
            "> 真源：`~/.claude/skills/project-delivery/常驻薄核.md`（版本化，git 跟踪）\n"
            "> 改规则去改真源，不要改这里。\n\n"
            "@~/.claude/skills/project-delivery/常驻薄核.md\n\n"
        )
        with open(launcher, "w", encoding="utf-8") as f:
            f.write(body + "\n".join(LAUNCHER_LINES) + "\n")
        print("[OK] 启动器已创建：%s" % launcher)

    if args.no_hooks:
        # 兜底必须出声：跳过了什么，当场说，别让人以为装全了
        print("[--] 按 --no-hooks 跳过 L0 强制层。规则仍然只写在文件里，没有东西会拦。")
    else:
        install_l0(claude_dir)

    ok = check(claude_dir, roots, None)
    print("")
    if ok:
        print("装好了。下一步：python -X utf8 %s" % os.path.join(BC, "dashboard.py"))
    else:
        print("装机自检有红——按上面 [!!] 逐条修（缺根的可以留 null）。")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
