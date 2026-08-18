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
import re
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

    # ---- 闭环：坑↔闸映射不许注水 -------------------------------------------
    # 守护率是个能靠瞎填变高的数——填一条假映射，缺闸清单就少一行，
    # 而那一行正是它该提醒你去建的东西。所以映射本身必须可证伪：
    # 坑号得真在坑库里，引用的文件得真在磁盘上。
    print("\n闭环映射（守护率能靠瞎填变高，这里让它不能）")
    mp = os.path.join(SRC_HOOKS, "pit_gate_map.json")
    s.check("pit_gate_map.json 在", os.path.isfile(mp), mp)
    if os.path.isfile(mp):
        with io.open(mp, encoding="utf-8") as f:
            mdoc = json.load(f)
        pit_md = os.path.join(SKILLS, "project-delivery", "坑库.md")
        ids = set()
        if os.path.isfile(pit_md):
            with io.open(pit_md, encoding="utf-8") as f:
                for ln in f:
                    m = re.match(r"^\|\s*([A-Z]+[0-9]+)\s*\|", ln)
                    if m:
                        ids.add(m.group(1))
        s.check("坑库解析出条目", len(ids) > 30, "只解析出 %d 条" % len(ids))

        ghosts = [k for k in mdoc.get("map", {}) if k not in ids]
        s.check("映射里没有不存在的坑号", not ghosts, "坑库里查无此条：%s" % ghosts)

        missing = []
        for pid, ent in mdoc.get("map", {}).items():
            for g in ent.get("guards", []):
                if g.startswith("R-L0-"):
                    continue          # 规则 ID，不是文件
                if not os.path.exists(os.path.join(SKILLS, g.replace("/", os.sep))):
                    missing.append("%s -> %s" % (pid, g))
        s.check("映射引用的守护文件都在", not missing, "找不到：%s" % missing[:4])

        rules = set()
        with io.open(os.path.join(SRC_HOOKS, "config.json"), encoding="utf-8") as f:
            for g in json.load(f)["gates"].values():
                rules.add(g["rule_id"])
        badrule = []
        for pid, ent in mdoc.get("map", {}).items():
            for g in ent.get("guards", []):
                if g.startswith("R-L0-") and not g.endswith("*") and g not in rules:
                    badrule.append("%s -> %s" % (pid, g))
        s.check("映射引用的闸门规则都存在", not badrule, "config 里没有：%s" % badrule)

    # ---- loop.ps1 / tally.ps1 跑得起来 -------------------------------------
    print("\n闭环工具")
    if IS_WIN:
        ps = shutil.which("powershell.exe") or shutil.which("powershell")
        for tool, needle in (("loop.ps1", "guard rate"), ("tally.ps1", "rule ledger")):
            r = subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                os.path.join(SRC_HOOKS, tool)],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            out = (r.stdout or b"").decode("utf-8", errors="replace")
            s.check("%s 跑得通且出数" % tool, needle in out, out[-160:])
    else:
        print("  (非 Windows，跳过 ps1 工具检查)")

    # ---- ASCII 不变式：ps1 里出现中文 = 上线即乱码 -------------------------
    # 这条不是洁癖。PowerShell 5.1 把无 BOM 的 UTF-8 脚本按 ANSI 读，
    # 脚本里的中文字面量会静默变成乱码；如果它出现在**判据**里
    # （曾经写过 -match '^\s*多'），匹配永远为假，而表面上什么都没坏。
    print("\nASCII 不变式（ps1 里写中文 = 判据静默失效）")
    for fn in ("gate.ps1", "tally.ps1", "loop.ps1"):
        p = os.path.join(SRC_HOOKS, fn)
        bad = []
        with io.open(p, encoding="utf-8") as f:
            for i, ln in enumerate(f, 1):
                if any(ord(c) > 126 for c in ln):
                    bad.append(i)
        s.check("%s 纯 ASCII" % fn, not bad, "非 ASCII 行：%s" % bad[:6])

    # ---- 一键装：settings.json 是用户的文件，只许增不许吃 -------------------
    # 手工粘配置对「陌生人第一次打开」这条判据等于不会发生，所以 L0 必须能一键装。
    # 而一键装碰的是用户存着权限配置的那个文件——装错的代价比不装大得多。
    print("\n一键装（--claude-dir 沙盒，真 settings.json 一个字节都不碰）")
    inst = os.path.join(BC, "install.py")
    if not os.path.isfile(inst):
        s.check("install.py 在", False, inst)
    else:
        def run_install(d):
            return subprocess.run(
                [sys.executable, "-X", "utf8", inst, "--claude-dir", d,
                 "--roots-file", os.path.join(d, "roots.json")],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            ).stdout.decode("utf-8", errors="replace")

        # ① 全新机器
        d1 = os.path.join(work, "cd_fresh")
        os.makedirs(d1)
        run_install(d1)
        sp = os.path.join(d1, "settings.json")
        conf = {}
        if os.path.isfile(sp):
            with io.open(sp, encoding="utf-8") as f:
                conf = json.load(f)
        evs = list(conf.get("hooks", {}).keys())
        s.check("全新机器 -> 三个事件都挂上",
                set(evs) >= {"SessionStart", "Stop", "PreToolUse"}, "实际：%s" % evs)

        # ② 幂等：装两次不许变成两条
        run_install(d1)
        with io.open(sp, encoding="utf-8") as f:
            conf2 = json.load(f)
        s.check("装第二次 -> 幂等不重复", len(conf2["hooks"]["Stop"]) == 1,
                "Stop 变成 %d 条" % len(conf2["hooks"]["Stop"]))

        # ③ 用户已有配置必须原样活着（反向断言：不是「没报错」，是「东西还在」）
        d2 = os.path.join(work, "cd_existing")
        os.makedirs(d2)
        with io.open(os.path.join(d2, "settings.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "permissions": {"defaultMode": "acceptEdits", "allow": ["Bash(git*)"]},
                "theme": "dark",
                "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "my-own.sh"}]}]},
            }, ensure_ascii=False, indent=2))
        run_install(d2)
        with io.open(os.path.join(d2, "settings.json"), encoding="utf-8") as f:
            c3 = json.load(f)
        s.check("已有 permissions 不被吃掉",
                c3.get("permissions", {}).get("defaultMode") == "acceptEdits", str(c3.get("permissions")))
        s.check("已有其它字段不被吃掉", c3.get("theme") == "dark", str(c3.get("theme")))
        cmds = [h["command"] for g in c3["hooks"]["Stop"] for h in g["hooks"]]
        s.check("用户自己的 hook 还在", "my-own.sh" in cmds, str(cmds))
        s.check("L0 追加在后面而不是替换", len(cmds) == 2, str(cmds))
        s.check("改之前留了备份", os.path.isfile(os.path.join(d2, "settings.json.before-l0")))

        # ④ 语法坏掉的 settings.json：一个字节都不许动，而且要出声
        d3 = os.path.join(work, "cd_broken")
        os.makedirs(d3)
        bp = os.path.join(d3, "settings.json")
        broken = '{ "permissions": { broken'
        with io.open(bp, "w", encoding="utf-8") as f:
            f.write(broken)
        out = run_install(d3)
        with io.open(bp, encoding="utf-8") as f:
            still = f.read()
        s.check("坏 settings.json -> 一个字节都不动", still == broken, still[:60])
        s.check("坏 settings.json -> 必须出声", "读不出来" in out, out[-160:])

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
