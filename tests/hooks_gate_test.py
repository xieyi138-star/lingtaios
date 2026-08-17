# -*- coding: utf-8 -*-
"""L0 强制层闸门回归（装配图 L0 · project-delivery/hooks/）

为什么要有它
------------
L0 是「规则真的会拦人」这件事的唯一实现。它坏了的表现有两种，而且都不吭声：
  · 全放行  —— 看起来一切正常，其实规则回到了纯自觉，和没装一样；
  · 全拦截  —— 每一轮回复都被打回，用户三分钟内就会把 hooks 从 settings.json 里删掉，
              于是永久失去闸门。

⛔ 闸门只绿过不算数。这里每条判据都成对写：一条证明它会拦，一条证明它不误拦。
   本层两个真 bug 都是被**反向**那条照出来的，正向那条全程绿着：
     ① [Console]::In 按 ANSI 解码 stdin → 中文证据头变乱码 → 合法回复也被拦
     ② $ErrorActionPreference='Stop' 把 git 的 stderr 当致命错 → 回滚点闸在
        它唯一要拦的场景里 100% 放行，还打出「git not runnable」这种错误归因
   只写正向断言的话，这两个都会一路绿到线上。

⛔ 演练不许碰真源：整个 hooks 目录先复制到临时目录，在副本上跑。
   真 traces 一个字节都不动。顺带也验了「换个位置还能不能跑」。

退出码：0 全绿 / 1 有红 / 3 这台机器上无从校验（没有可用的 shell）
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 两种布局都要认（soul_manifest.py 同款判定，改一个必须改另一个）：
#   主源码  skills\brain-console\  → project-delivery 在上一级
#   发布仓  repo\                  → project-delivery 在同级
SKILLS = BC if os.path.isdir(os.path.join(BC, "project-delivery")) else os.path.dirname(BC)
SRC_HOOKS = os.path.join(SKILLS, "project-delivery", "hooks")

IS_WIN = os.name == "nt"


def _runner(hook_dir):
    """返回 (argv 前缀, 说明)；这台机器上跑不了任何一版就返回 (None, 原因)。"""
    if IS_WIN:
        ps = shutil.which("powershell.exe") or shutil.which("powershell")
        if ps:
            return ([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                     os.path.join(hook_dir, "gate.ps1")], "gate.ps1 / PowerShell")
    sh = shutil.which("bash")
    if sh:
        return ([sh, os.path.join(hook_dir, "gate.sh")], "gate.sh / bash")
    return (None, "既没有 powershell 也没有 bash")


def call(argv, payload):
    """喂一份 hook 输入，拿回 (stdout 文本, 退出码)。stdin 必须是 UTF-8 字节。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    r = subprocess.run(argv, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return ((r.stdout or b"").decode("utf-8", errors="replace").strip(), r.returncode)


class Suite(object):
    def __init__(self):
        self.rows = []

    def check(self, name, cond, detail=""):
        self.rows.append((name, bool(cond), detail))
        print("  %-46s %s%s" % (name, "OK" if cond else "FAIL",
                                ("  <- " + detail[:90]) if (detail and not cond) else ""))
        return bool(cond)

    @property
    def failed(self):
        return [n for n, ok, _ in self.rows if not ok]


def main():
    if not os.path.isdir(SRC_HOOKS):
        print("[XX] 找不到 L0 目录：%s" % SRC_HOOKS)
        print("[FAIL] 装配图 L0 登记了这个目录，实盘没有")
        sys.exit(1)

    work = tempfile.mkdtemp(prefix="l0gate_")
    hook_dir = os.path.join(work, "hooks")
    shutil.copytree(SRC_HOOKS, hook_dir,
                    ignore=shutil.ignore_patterns("traces", "__pycache__"))

    argv, how = _runner(hook_dir)
    if argv is None:
        print("[跳过] %s——这台机器上无从校验" % how)
        sys.exit(3)
    print("跑的是：%s" % how)
    print("沙盒：%s（真 traces 不受影响）\n" % hook_dir)

    s = Suite()
    hdr = "【证据】Read config.json → master_switch=true"

    # ---- R-L0-001 证据头：正反成对 ----------------------------------------
    print("R-L0-001 证据头")
    out, _ = call(argv, {"hook_event_name": "Stop", "session_id": "t1",
                         "last_assistant_message": "我把解析器改好了。"})
    s.check("缺证据头 -> 必须拦", '"decision":"block"' in out, out)

    out, _ = call(argv, {"hook_event_name": "Stop", "session_id": "t2",
                         "last_assistant_message": hdr + "\n\n做完了。"})
    s.check("有【证据】头 -> 必须放行（反向）", out == "", out)

    out, _ = call(argv, {"hook_event_name": "Stop", "session_id": "t3",
                         "last_assistant_message": "【无证据】已查 A B C 均无 → 以下为推测"})
    s.check("有【无证据】头 -> 必须放行（反向）", out == "", out)

    out, _ = call(argv, {"hook_event_name": "Stop", "session_id": "t4",
                         "last_assistant_message": ""})
    s.check("空回复（只调了工具）-> 不算违规", out == "", out)

    out, _ = call(argv, {"hook_event_name": "Stop", "session_id": "t5",
                         "last_assistant_message": "\n\n" + hdr})
    s.check("证据头前有空行 -> 取首个非空行", out == "", out)

    # ---- 防死循环：拦到上限必须放行，且放行本身要被看见 --------------------
    print("\n防死循环")
    seen = []
    for i in range(4):
        out, _ = call(argv, {"hook_event_name": "Stop", "session_id": "loop",
                             "last_assistant_message": "still no header"})
        seen.append(out)
    s.check("前两次拦住", '"decision":"block"' in seen[0] and '"decision":"block"' in seen[1],
            seen[0][:60])
    s.check("到上限强制放行（不死循环）", '"decision":"block"' not in seen[2], seen[2][:80])
    s.check("放行必须出声（不许静默）", "systemMessage" in seen[2], seen[2][:80])

    # ---- R-L0-002 红线短语：只记账不拦 -------------------------------------
    print("\nR-L0-002 红线短语")
    out, _ = call(argv, {"hook_event_name": "Stop", "session_id": "t6",
                         "last_assistant_message": hdr + "\n\n这个应该是对的，我记得改过。"})
    s.check("命中红线短语 -> 出声", "systemMessage" in out, out)
    s.check("命中红线短语 -> 不拦（硬拦会逼出规避性改写）",
            '"decision":"block"' not in out, out)

    out, _ = call(argv, {"hook_event_name": "Stop", "session_id": "t7",
                         "last_assistant_message": hdr + "\n\n改完了，回读验过。"})
    s.check("没有红线短语 -> 不该出声（反向）", out == "", out)

    # ---- R-L0-003 回滚点 ----------------------------------------------------
    print("\nR-L0-003 回滚点")
    nogit = os.path.join(work, "project-delivery")
    os.makedirs(nogit)
    out, _ = call(argv, {"hook_event_name": "PreToolUse", "session_id": "t8",
                         "tool_name": "Write",
                         "tool_input": {"file_path": os.path.join(nogit, "x.md")}})
    s.check("核心真源 + 不在 git 下 -> 必须拦", '"permissionDecision":"deny"' in out, out)

    ingit = os.path.join(SKILLS, "project-delivery", "hooks", "config.json")
    out, _ = call(argv, {"hook_event_name": "PreToolUse", "session_id": "t9",
                         "tool_name": "Write", "tool_input": {"file_path": ingit}})
    s.check("核心真源 + 在 git 下 -> 必须放行（反向）", out == "", out)

    out, _ = call(argv, {"hook_event_name": "PreToolUse", "session_id": "t10",
                         "tool_name": "Write",
                         "tool_input": {"file_path": os.path.join(work, "unrelated.txt")}})
    s.check("非核心文件 -> 不进闸（反向）", out == "", out)

    # ---- R-L0-004 不可逆命令 ------------------------------------------------
    print("\nR-L0-004 不可逆命令")
    # 拼出来而不是写字面量：这个文件自己也会被闸门扫到（实测拦过一次）
    danger = "git " + "reset" + " --hard HEAD~3"
    out, _ = call(argv, {"hook_event_name": "PreToolUse", "session_id": "t11",
                         "tool_name": "Bash", "tool_input": {"command": danger}})
    s.check("不可逆命令 -> 第一次必须拦", '"permissionDecision":"deny"' in out, out)

    out, _ = call(argv, {"hook_event_name": "PreToolUse", "session_id": "t11",
                         "tool_name": "Bash", "tool_input": {"command": danger}})
    s.check("同 session 重发同一条 -> 放行（说明回滚路径后）", out == "", out)

    out, _ = call(argv, {"hook_event_name": "PreToolUse", "session_id": "t12",
                         "tool_name": "Bash", "tool_input": {"command": "git status --short"}})
    s.check("安全命令 -> 不进闸（反向）", out == "", out)

    out, _ = call(argv, {"hook_event_name": "PreToolUse", "session_id": "t13",
                         "tool_name": "Bash",
                         "tool_input": {"command": "git push --force-with-lease origin main"}})
    s.check("--force-with-lease -> 放行（它自带回滚点意识）", out == "", out)

    # ---- R-L0-005 开窗注入 --------------------------------------------------
    print("\nR-L0-005 开窗注入")
    out, _ = call(argv, {"hook_event_name": "SessionStart", "session_id": "t14",
                         "startup_type": "startup"})
    s.check("SessionStart -> 注入非空", len(out) > 50, out[:80])
    s.check("注入里带生效闸清单", "R-L0-001" in out, out[:120])

    # ---- traces 真的写下去了没有 -------------------------------------------
    print("\n记账（规则台账那两栏的真值来源）")
    tdir = os.path.join(hook_dir, "traces")
    lines = []
    if os.path.isdir(tdir):
        for fn in os.listdir(tdir):
            if fn.endswith(".jsonl"):
                with io.open(os.path.join(tdir, fn), encoding="utf-8") as f:
                    lines += [ln for ln in f.read().splitlines() if ln.strip()]
    s.check("触发有落盘", len(lines) > 0, "traces 一行都没有")
    acts = set()
    bad = 0
    for ln in lines:
        try:
            acts.add(json.loads(ln).get("action"))
        except ValueError:
            bad += 1
    s.check("每行都是合法 JSON", bad == 0, "%d 行解析失败" % bad)
    for a in ("block", "warn", "deny", "released", "pass_on_retry"):
        s.check("记到了 action=%s" % a, a in acts, "实际有：%s" % sorted(acts))

    # ---- 开关：关了必须全放行，而且必须喊出来 -------------------------------
    print("\n总开关（关掉后必须出声——静默失效的闸比没有闸更贵）")
    cfgp = os.path.join(hook_dir, "config.json")
    with io.open(cfgp, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["master_switch"] = False
    with io.open(cfgp, "w", encoding="utf-8") as f:
        f.write(json.dumps(cfg, ensure_ascii=False, indent=2))

    out, _ = call(argv, {"hook_event_name": "Stop", "session_id": "t15",
                         "last_assistant_message": "no header at all"})
    s.check("master_switch=false -> 不再拦", '"decision":"block"' not in out, out)
    s.check("master_switch=false -> 必须出声", "systemMessage" in out, out)

    # ---- 配置损坏：fail-open，但要喊 ---------------------------------------
    print("\n配置损坏（闸门自己坏了不许挡住人干活，但不许不吭声）")
    with io.open(cfgp, "w", encoding="utf-8") as f:
        f.write("{ this is not json")
    out, code = call(argv, {"hook_event_name": "Stop", "session_id": "t16",
                            "last_assistant_message": "no header"})
    s.check("配置坏了 -> 不拦（fail-open）", '"decision":"block"' not in out, out)
    s.check("配置坏了 -> 必须出声", "systemMessage" in out, out)
    s.check("配置坏了 -> 退出码仍是 0（不能挡住工具链）", code == 0, "exit=%s" % code)

    shutil.rmtree(work, ignore_errors=True)

    print("\n" + "=" * 62)
    total = len(s.rows)
    if s.failed:
        print("[FAIL] %d/%d 条不过：%s" % (len(s.failed), total, ", ".join(s.failed)))
        sys.exit(1)
    print("[OK] L0 闸门 %d 条判据全过（每条硬拦都配了反向断言）" % total)
    sys.exit(0)


if __name__ == "__main__":
    main()
