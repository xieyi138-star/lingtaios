# -*- coding: utf-8 -*-
"""把 L0 强制层挂进 Claude Code 的 settings.json —— 挂载逻辑的**唯一实现**。

为什么单独一个文件
------------------
它有三个调用方，而三个都得是同一套行为：

  1. `install.py`（源码态：clone 下来 / skills 仓）—— 换电脑第一条命令
  2. `lingtaios.exe --install-hooks`（发布态）—— exe 用户手里没有 install.py
  3. `python mount.py`（直接跑）—— 两样都没有时的兜底

⛔ 抄第二份必分叉（坑库 P10）。尤其是「不覆盖用户配置」这类判据抄错一次的代价，
   是把别人存着权限配置的文件写坏——比不装贵得多。

⛔ 这个文件用 Python，而 hooks/ 下的闸门本体（gate.ps1 / gate.sh）刻意零 Python 依赖。
   两者不矛盾：闸门在**每次回复**时跑，不能要求用户装 Python；挂载只在**装机时**跑一次，
   而那时调用方本身就是 Python（install.py / exe 自带运行时）。

用法:
    python -X utf8 mount.py            # 挂到 ~/.claude
    python -X utf8 mount.py --check    # 只查不写
    python -X utf8 mount.py --claude-dir <path>   # 覆盖落点（演练/测试）
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# hooks/ 的上上级就是方法层根（project-delivery 的父目录）
REPO = os.path.dirname(os.path.dirname(HERE))

# 挂到哪些事件。matcher 只在 PreToolUse 有意义。
# ⛔ 不写 "*"：那等于每次工具调用都启一个进程（约 200-300ms），
#    而 Read/Grep/Glob 这类高频只读操作根本不需要进闸。
EVENTS = [
    ("SessionStart", None),
    ("Stop", None),
    ("PreToolUse", "Write|Edit|NotebookEdit|Bash|PowerShell"),
]


def handler(hook_dir=None):
    """本平台跑闸门的命令。Windows 走 gate.ps1，其余走 gate.sh。"""
    d = hook_dir or HERE
    if os.name == "nt":
        return {
            "type": "command",
            "command": "powershell.exe",
            "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                     os.path.join(d, "gate.ps1")],
            "timeout": 20,
        }
    return {"type": "command", "command": "bash",
            "args": [os.path.join(d, "gate.sh")], "timeout": 20}


def _gate_path(h):
    a = h.get("args") or []
    return a[-1] if a else ""


def status(claude_dir, hook_dir=None):
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
    want = os.path.normcase(_gate_path(handler(hook_dir)))
    for ev, _m in EVENTS:
        hit = any(os.path.normcase(_gate_path(h)) == want
                  for grp in (conf.get("hooks", {}).get(ev) or [])
                  for h in (grp.get("hooks") or []))
        if not hit:
            return (False, "缺 %s 这一挂" % ev)
    return (True, "三个事件都挂着")


def mount(claude_dir, hook_dir=None, quiet=False):
    """挂上去。**只增不覆盖**——settings.json 是用户自己的文件。

    ⛔ 已有的 hooks 一条都不动，只往对应事件的数组里追加自己那条；
       已经挂过就什么都不做（幂等）。
    ⛔ 写走「先写 .tmp、读回验证、再 os.replace」（坑库 T15：
       open(...,'w') 是先截断后写，中途失败原文件就没了）。
    """
    def say(*a):
        if not quiet:
            print(*a)

    p = os.path.join(claude_dir, "settings.json")
    conf = {}
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8-sig") as f:
                conf = json.load(f)
        except (OSError, ValueError) as e:
            say("[!!] settings.json 存在但读不出来（%s）——L0 没装。" % e.__class__.__name__)
            say("     不动它是故意的：这个文件里还有你的权限配置，"
                "覆盖掉比不装 L0 贵得多。修好语法再跑一次。")
            return False
        bak = p + ".before-l0"
        if not os.path.isfile(bak):
            with open(bak, "w", encoding="utf-8") as f:
                json.dump(conf, f, ensure_ascii=False, indent=2)
            say("[OK] 原 settings.json 已备份：%s" % bak)

    h = handler(hook_dir)
    gp = _gate_path(h)
    if not os.path.isfile(gp):
        say("[XX] 找不到闸门脚本：%s" % gp)
        return False

    hooks = conf.setdefault("hooks", {})
    want = os.path.normcase(gp)
    added = []
    for ev, matcher in EVENTS:
        arr = hooks.setdefault(ev, [])
        if any(os.path.normcase(_gate_path(x)) == want
               for grp in arr for x in (grp.get("hooks") or [])):
            continue
        grp = {"hooks": [dict(h)]}
        if matcher:
            grp["matcher"] = matcher
        arr.append(grp)
        added.append(ev)

    if not added:
        say("[OK] L0 已经挂着，未改动 settings.json")
        return True

    if not os.path.isdir(claude_dir):
        os.makedirs(claude_dir)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(conf, f, ensure_ascii=False, indent=2)
    with open(tmp, encoding="utf-8") as f:   # 先证明新文件读得回来，再动旧的
        json.load(f)
    os.replace(tmp, p)
    say("[OK] L0 已挂上：%s（新增 %s）" % (p, ", ".join(added)))
    say("     关掉它：改 %s 的 master_switch 为 false" %
        os.path.join(hook_dir or HERE, "config.json"))
    say("     需要重开一个 Claude Code 会话才生效")
    return True


def main():
    ap = argparse.ArgumentParser(description="挂载 L0 强制层")
    ap.add_argument("--claude-dir", help="覆盖 ~/.claude 落点（演练/测试）")
    ap.add_argument("--hook-dir", help="覆盖 hooks 目录（默认本文件所在目录）")
    ap.add_argument("--check", action="store_true", help="只查不写")
    args = ap.parse_args()
    cd = args.claude_dir or os.path.join(os.path.expanduser("~"), ".claude")
    ok, why = status(cd, args.hook_dir)
    if args.check:
        print(("[OK] L0 已挂载（%s）" if ok else "[!!] L0 未挂载：%s") % why)
        sys.exit(0 if ok else 1)
    sys.exit(0 if mount(cd, args.hook_dir) else 1)


if __name__ == "__main__":
    main()
