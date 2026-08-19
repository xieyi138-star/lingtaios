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


FORCE_SH = "--sh" in sys.argv


def _runner(hook_dir):
    """返回 (argv 前缀, 说明)；这台机器上跑不了任何一版就返回 (None, 原因)。

    平时按平台选：Windows 走 gate.ps1，其余走 gate.sh。所以 mac/Linux 用户
    跑这个脚本，验的自然就是他那一份——**这就是 gate.sh 的验证方式**，
    作者手上没有 POSIX 机器，验不了的那部分只能交给能验的人。

    `--sh` 强制走 gate.sh：在 Windows 的 Git Bash 下也能把这套判据压给它跑一遍。
    ⛔ 那不等于「在真 POSIX 上验过了」——Git Bash 不是 Linux，用的还是 Windows
       的 python 和路径语义。它只能证明「测试代码驱动得动 gate.sh、判据逻辑对得上」，
       证明不了 bash/coreutils 的行为差异。这个区别必须留在嘴上，别在文档里说漏。
    """
    if IS_WIN and not FORCE_SH:
        ps = shutil.which("powershell.exe") or shutil.which("powershell")
        if ps:
            return ([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                     os.path.join(hook_dir, "gate.ps1")], "gate.ps1 / PowerShell")
    sh = shutil.which("bash")
    if sh:
        tag = "gate.sh / bash"
        if IS_WIN:
            tag += "（Windows 上的 Git Bash——不等于真 POSIX）"
        return ([sh, os.path.join(hook_dir, "gate.sh")], tag)
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

    # ---- R-L0-006 声称生效必须有实查（坑库 S3，全库咬得最多的一条）----------
    # 判据是两个条件的**合取**：回复里有生效类断言，且这一轮零次查询工具调用。
    # 所以反向断言有两条，缺一不可：查过了要放行、没声称也要放行。
    print("\nR-L0-006 声称生效必须有实查（坑库 S3，六起同形）")
    tdir = os.path.join(work, "transcripts")
    os.makedirs(tdir)

    def mk(name, rows):
        p = os.path.join(tdir, name)
        with io.open(p, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return p

    human = {"type": "user", "message": {"content": "装好了吗"}}
    used = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {}}]}}
    tres = {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}}
    plain = {"type": "assistant", "message": {"content": [{"type": "text", "text": "..."}]}}
    wrote = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Write", "input": {}}]}}

    t_noq = mk("noq.jsonl", [human, used, tres, human, plain])
    t_q = mk("q.jsonl", [human, plain, human, used, tres])
    t_write = mk("w.jsonl", [human, plain, human, wrote, tres])

    def stop_claim(sid, tpath, text):
        return call(argv, {"hook_event_name": "Stop", "session_id": sid,
                           "transcript_path": tpath,
                           "last_assistant_message": hdr + "\n\n" + text})[0]

    out = stop_claim("c1", t_noq, "L0 已生效，服务正常。")
    s.check("声称生效 + 本轮零实查 -> 必须拦", "R-L0-006" in out, out[:120])

    out = stop_claim("c2", t_q, "L0 已生效。")
    s.check("声称生效 + 本轮查过 -> 放行（反向）", out == "", out[:120])

    out = stop_claim("c3", t_noq, "改完了，下一步继续。")
    s.check("没有声称 -> 不进这条闸（反向）", out == "", out[:120])

    # 写了 != 验了（坑库 S2）。Write 不在 verify_tools 里，所以仍该拦。
    out = stop_claim("c4", t_write, "L0 已生效。")
    s.check("本轮只 Write 没读 -> 仍要拦（写了不等于验了）", "R-L0-006" in out, out[:120])

    out = stop_claim("c5", os.path.join(tdir, "does_not_exist.jsonl"), "L0 已生效。")
    s.check("transcript 读不到 -> 不拦（判不出不等于有罪）", "decision" not in out, out[:120])
    s.check("transcript 读不到 -> 必须出声", "systemMessage" in out, out[:120])

    # ---- R-L0-007 python 不带 -X utf8（坑库 T2，已咬两次）-------------------
    # T2 两次都是**在别人的机器上才炸**：BOM 破 ^ 锚定正则、CI 的 windows runner
    # stdout 默认 cp1252。本机默认编码碰巧对，所以这类错在这儿永远复现不了。
    # 判据窄而明确，误报面小——但正因为窄，反向断言更重要：拦过头会把
    # python -c / -m / 已豁免的一起拦掉，那就成了每天挡路的闸。
    print("\nR-L0-007 python 不带 -X utf8（坑库 T2）")
    _py = "py" + "thon"      # 拼出来：这个文件自己也会被这条闸扫到

    def bash_cmd(sid, cmd):
        return call(argv, {"hook_event_name": "PreToolUse", "session_id": sid,
                           "tool_name": "Bash", "tool_input": {"command": cmd}})[0]

    out = bash_cmd("e1", "%s tests/x.py" % _py)
    s.check("跑脚本没带 -X utf8 -> 拦", "R-L0-007" in out, out[:100])

    out = bash_cmd("e2", "%s -X utf8 tests/x.py" % _py)
    s.check("带了 -X utf8 -> 放行（反向）", out == "", out[:100])

    out = bash_cmd("e3", '%s -c "print(1)"' % _py)
    s.check("-c 不跑脚本文件 -> 放行（反向）", out == "", out[:100])

    out = bash_cmd("e4", "%s -m pytest" % _py)
    s.check("-m 模块 -> 放行（反向）", out == "", out[:100])

    out = bash_cmd("e5", "PYTHONUTF8=1 %s x.py" % _py)
    s.check("环境变量已豁免 -> 放行（反向）", out == "", out[:100])

    out = bash_cmd("e6", "node x.js")
    s.check("非 python 命令 -> 不进这条闸（反向）", out == "", out[:100])

    # ---- R-L0-005 开窗注入 --------------------------------------------------
    print("\nR-L0-005 开窗注入")
    out, _ = call(argv, {"hook_event_name": "SessionStart", "session_id": "t14",
                         "startup_type": "startup"})
    s.check("SessionStart -> 注入非空", len(out) > 50, out[:80])
    s.check("注入里带生效闸清单", "R-L0-001" in out, out[:120])

    # ---- 宿主适配层：同一条判据，不同宿主的输出形状 -------------------------
    # L0 的价值是「规则在模型外面被拦住」，不是「只能在 Claude Code 里被拦住」。
    # 判据与宿主无关，被锁死的只有输入字段名和阻断输出的形状——两者都在 config.json。
    # ⛔ 这几条验的是**适配层没把判据带歪**：换个宿主，该拦的仍拦、该放的仍放。
    # ⛔ 必须跑在「总开关」和「配置损坏」那两节**之前**——那两节会把沙盒里的
    #    config.json 改坏，之后所有 gate 调用都走 fail-open 分支。
    #    第一版就加在了它们后面，6 条全红，而手工跑同样的输入是通的。
    print("\n宿主适配（同一判据，不同宿主）")
    if IS_WIN and not FORCE_SH:
        _ps = shutil.which("powershell.exe") or shutil.which("powershell")

        def gate(hostname, event, payload):
            argv2 = [_ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                     os.path.join(hook_dir, "gate.ps1"), "-HostName", hostname]
            if event:
                argv2 += ["-EventName", event]
            return call(argv2, payload)[0]

        out = gate("cursor", "stop", {"session_id": "cu1", "text": "我改好了。"})
        s.check("cursor: 缺证据头 -> 拦", '"permission":"deny"' in out, out[:120])
        s.check("cursor: 用 cursor 的输出形状（不是 claude 的）",
                '"agent_message"' in out and '"decision"' not in out, out[:120])

        out = gate("cursor", "stop", {"session_id": "cu2", "text": hdr + "\n\n做完了。"})
        s.check("cursor: 有证据头 -> 放行（反向）", out == "", out[:120])

        # Cursor 的 beforeShellExecution 只给 command，没有 tool_name。
        # 判据要是依赖工具名，换宿主就静默失效——拦不住，而且没人会知道。
        danger = "rm " + "-rf" + " /tmp/zz"
        out = gate("cursor", "beforeShellExecution", {"session_id": "cu3", "command": danger})
        s.check("cursor: 只给 command 没给 tool_name -> 仍拦得住",
                '"permission":"deny"' in out, out[:120])

        out = gate("cursor", "beforeShellExecution",
                   {"session_id": "cu4", "command": "git status --short"})
        s.check("cursor: 安全命令 -> 放行（反向）", out == "", out[:120])

        out = gate("nope", None, {"hook_event_name": "Stop", "session_id": "cu5",
                                  "last_assistant_message": "x"})
        s.check("未知宿主 -> 不拦但出声（不许静默失效）",
                "systemMessage" in out and "unknown host" in out, out[:120])

        # 每个宿主都得说清自己验没验过。没这一栏的话，「作者实测过」和
        # 「照着文档写的」在用户眼里长得一模一样。
        with io.open(os.path.join(SRC_HOOKS, "config.json"), encoding="utf-8") as f:
            hosts = json.load(f)["hosts"]
        bad = [k for k, v in hosts.items()
               if not k.startswith("_") and "verified" not in v]
        s.check("每个宿主都标了验没验过", not bad, "缺 verified：%s" % bad)
    else:
        print("  (非 Windows / --sh 模式，跳过 ps1 宿主适配检查)")

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

        # 主源码布局的判据和 soul_manifest / install.py / spec 同源
        FLAT = not os.path.isdir(os.path.join(SKILLS, "brain-console"))

        def guard_exists(rel):
            """两种布局都要认：
              主源码  skills\\brain-console\\  → 路径是 brain-console/tests/x.py
              发布仓  repo\\                   → 发布时摊平，同一件在 tests/x.py
            ⛔ 只认第一种的话，从公开仓 clone 下来跑，这条断言会把**存在的**文件
               报成缺失——正是坑库 P23 的形状。实测：发布仓布局下当场红。

            `internal:` 前缀 = 这个守护者不随包分发（如 release_sync.py 在
            NOT_SHIPPED 上）。发布仓里它本来就不该在，跳过存在检查。
            ⛔ 跳过的只是**检查**，不是事实：那条坑在用户手上确实没人守，
               守护率对他是虚高的。这一点写在 pit_gate_map 的说明里，别忘了。
            """
            if rel.startswith("internal:"):
                if FLAT:
                    return True
                rel = rel[len("internal:"):]
            cands = [rel]
            if rel.startswith("brain-console/"):
                cands.append(rel[len("brain-console/"):])
            return any(os.path.exists(os.path.join(SKILLS, c.replace("/", os.sep)))
                       for c in cands)

        missing = []
        for pid, ent in mdoc.get("map", {}).items():
            for g in ent.get("guards", []):
                if g.startswith("R-L0-"):
                    continue          # 规则 ID，不是文件
                if not guard_exists(g):
                    missing.append("%s -> %s" % (pid, g))
        s.check("映射引用的守护文件都在（两种布局）", not missing, "找不到：%s" % missing[:4])

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
        # tally 在**还没有任何 traces** 时不打表头，而是提示「一条流水都没有，
        # 先确认闸门接上了」——那是正确行为，不是失败。发布仓里 traces/ 不同步
        # （SKIP_NAMES），所以从 clone 出来跑必然走这一支。只认表头那个词的话，
        # 这条断言在别人机器上必红，而产品完全正常。
        for tool, needles in (("loop.ps1", ["guard rate"]),
                              ("tally.ps1", ["rule ledger", "no traces yet"])):
            r = subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                os.path.join(SRC_HOOKS, tool)],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            out = (r.stdout or b"").decode("utf-8", errors="replace")
            s.check("%s 跑得通且出数" % tool, any(n in out for n in needles), out[-160:])
    else:
        print("  (非 Windows，跳过 ps1 工具检查)")

    # ---- ASCII 不变式：ps1 里出现中文 = 上线即乱码 -------------------------
    # 这条不是洁癖。PowerShell 5.1 把无 BOM 的 UTF-8 脚本按 ANSI 读，
    # 脚本里的中文字面量会静默变成乱码；如果它出现在**判据**里
    # （曾经写过 -match '^\s*多'），匹配永远为假，而表面上什么都没坏。
    print("\nASCII 不变式（ps1 里写中文 = 判据静默失效）")
    for fn in ("gate.ps1", "tally.ps1", "loop.ps1", "gate.sh"):
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

        # ⑤ 三个入口必须产出同一份配置。
        # mount.py 是唯一实现，install.py 和 exe 的 --install-hooks 都调它——
        # 但「都调它」这句话本身要能被证伪，否则哪天有人图省事在某一边抄一份，
        # 分叉了也没人知道（坑库 P10：同一判据抄多份必分叉，曾抄了 28 份）。
        mountpy = os.path.join(SRC_HOOKS, "mount.py")
        dash = os.path.join(BC, "dashboard.py")
        outs = {}
        for tag, argv2 in (
            ("mount", [sys.executable, "-X", "utf8", mountpy]),
            ("dashboard", [sys.executable, "-X", "utf8", dash, "--install-hooks"]),
        ):
            d = os.path.join(work, "cd_" + tag)
            os.makedirs(d)
            subprocess.run(argv2 + ["--claude-dir", d],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            p = os.path.join(d, "settings.json")
            if os.path.isfile(p):
                with io.open(p, encoding="utf-8") as f:
                    outs[tag] = json.dumps(json.load(f), sort_keys=True, ensure_ascii=False)
        with io.open(os.path.join(d1, "settings.json"), encoding="utf-8") as f:
            outs["install"] = json.dumps(json.load(f), sort_keys=True, ensure_ascii=False)
        s.check("mount.py 与 install.py 产出一致",
                outs.get("mount") and outs.get("mount") == outs.get("install"),
                "mount=%s" % str(outs.get("mount"))[:80])
        s.check("dashboard --install-hooks 与 install.py 产出一致",
                outs.get("dashboard") and outs.get("dashboard") == outs.get("install"),
                "dashboard=%s" % str(outs.get("dashboard"))[:80])

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
