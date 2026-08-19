# -*- coding: utf-8 -*-
"""L0 强制层压测：长期跑会不会把自己撑坏、会不会把人拖慢

为什么单独一条
--------------
`hooks_gate_test.py` 验的是**判据对不对**（拦该拦的、放该放的）。
它一条都不回答下面这些问题，而这些恰恰是「装上以后用三个月」才会暴露的：

  · 每次触发写一行流水、每个会话留一个计数文件——**从来没有东西删它们**
  · 闸门跑在每一次回复和每一次写文件之前，慢一点就是全局慢
  · 用户开三个窗口并行干活时，三个闸门进程同时写同一份流水
  · 超长回复 / 超大 transcript / 超长命令，正则会不会退化

⛔ 这类问题的共同点：**功能全绿的时候它们已经在积累了**。
   等到有人反馈「越用越慢」「C 盘满了」，损失已经发生。

判据（不是「跑得快」这种过程量）：
  1. 单次闸门调用 < 2s（hook 超时 20s，留 10 倍余量）
  2. 并发写流水后，每一行仍是合法 JSON，且总行数 = 实际触发次数（不丢不串行）
  3. 磁盘增长有**上限机制**，不是只有增长率
  4. 超长输入不触发正则退化（同一判据 100 倍输入，耗时不许涨 100 倍）

⛔ 演练不许碰真源：整个 hooks 目录复制到临时目录跑，真 traces 一个字节不动。

退出码：0 全过 / 1 有红 / 3 无从校验
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = BC if os.path.isdir(os.path.join(BC, "project-delivery")) else os.path.dirname(BC)
SRC_HOOKS = os.path.join(SKILLS, "project-delivery", "hooks")
IS_WIN = os.name == "nt"

rows = []


def check(name, ok, detail="", note=""):
    """detail 只在**失败**时打，note 任何时候都打。

    ⛔ 两者混成一个参数会让绿行显示红话：实测出现过
       「过期流水被清掉  OK  2020-01-01.jsonl 还在」——一行里前半句说过了、
       后半句说没删，读的人只能停下来猜哪半句是真的。
       量具自己的输出误导人，和量错了一样贵。
    """
    rows.append((name, bool(ok)))
    tail = ("  " + str(note)[:60]) if note else ""
    if not ok and detail:
        tail = "  <- " + str(detail)[:100]
    print("  %-50s %s%s" % (name, "OK" if ok else "FAIL", tail))


def runner(hook_dir):
    if IS_WIN:
        ps = shutil.which("powershell.exe") or shutil.which("powershell")
        if ps:
            return [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    os.path.join(hook_dir, "gate.ps1")]
    sh = shutil.which("bash")
    if sh:
        return [sh, os.path.join(hook_dir, "gate.sh")]
    return None


def call(argv, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    t0 = time.time()
    r = subprocess.run(argv, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return (time.time() - t0, (r.stdout or b"").decode("utf-8", errors="replace"))


def main():
    if not os.path.isdir(SRC_HOOKS):
        print("[XX] 找不到 L0 目录：%s" % SRC_HOOKS)
        sys.exit(1)
    work = tempfile.mkdtemp(prefix="l0stress_")
    hook_dir = os.path.join(work, "hooks")
    shutil.copytree(SRC_HOOKS, hook_dir, ignore=shutil.ignore_patterns("traces", "__pycache__"))
    argv = runner(hook_dir)
    if argv is None:
        print("[跳过] 既没有 powershell 也没有 bash")
        sys.exit(3)
    tdir = os.path.join(hook_dir, "traces")
    sdir = os.path.join(tdir, ".state")
    hdr = "【证据】Read x → ok"

    # ---- 1. 单次耗时 --------------------------------------------------------
    print("\n[1] 单次闸门耗时（hook 超时 20s，判据 < 2s）")
    dt_stop, _ = call(argv, {"hook_event_name": "Stop", "session_id": "p1",
                             "last_assistant_message": hdr})
    check("Stop 放行", dt_stop < 2.0, note="%.2fs" % dt_stop)
    dt_blk, _ = call(argv, {"hook_event_name": "Stop", "session_id": "p2",
                            "last_assistant_message": "no header"})
    check("Stop 拦截", dt_blk < 2.0, note="%.2fs" % dt_blk)
    dt_tool, _ = call(argv, {"hook_event_name": "PreToolUse", "session_id": "p3",
                             "tool_name": "Bash", "tool_input": {"command": "git status"}})
    check("PreToolUse 放行", dt_tool < 2.0, note="%.2fs" % dt_tool)

    # ---- 2. 超长输入不许让正则退化 -------------------------------------------
    # 判据不是绝对耗时，是**相对**：输入涨 100 倍，耗时不许也涨 100 倍。
    # 绝对值会被机器快慢带偏，相对值才照得出算法本身的退化。
    print("\n[2] 超长输入（同一判据，100 倍输入）")
    big_msg = hdr + "\n\n" + ("这是一段很长的正常回复内容。" * 4000)   # ~100KB
    dt_big, _ = call(argv, {"hook_event_name": "Stop", "session_id": "p4",
                            "last_assistant_message": big_msg})
    check("100KB 回复 < 3s", dt_big < 3.0, note="%.2fs（基线 %.2fs）" % (dt_big, dt_stop))
    ratio = dt_big / max(dt_stop, 0.01)
    check("耗时没有随输入线性爆炸（<10x）", ratio < 10, note="%.1fx" % ratio)

    # 15 条 danger 正则 × 超长命令：ReDoS 的典型触发面
    big_cmd = ("git status && " * 800) + "echo done"                  # ~10KB
    dt_cmd, _ = call(argv, {"hook_event_name": "PreToolUse", "session_id": "p5",
                            "tool_name": "Bash", "tool_input": {"command": big_cmd}})
    check("10KB 命令过 15 条正则 < 3s", dt_cmd < 3.0, note="%.2fs" % dt_cmd)

    # ---- 3. 超大 transcript（R-L0-006 要读它）--------------------------------
    print("\n[3] 超大 transcript")
    tp = os.path.join(work, "big_transcript.jsonl")
    with io.open(tp, "w", encoding="utf-8") as f:
        for i in range(12000):
            f.write(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Read", "input": {}}]}}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"type": "user", "message": {"content": "go"}}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {}}]}}, ensure_ascii=False) + "\n")
    dt_tr, out_tr = call(argv, {"hook_event_name": "Stop", "session_id": "p6",
                                "transcript_path": tp,
                                "last_assistant_message": hdr + "\n\nL0 已生效。"})
    check("12000 行 transcript < 5s", dt_tr < 5.0, note="%.2fs" % dt_tr)
    # 最后一次真人输入之后确实查过 -> 不该拦。拦了说明扫描窗口没覆盖到边界。
    check("超大 transcript 下判据仍正确（查过 -> 放行）", "R-L0-006" not in out_tr, out_tr[:80])

    # ---- 4. 并发写流水 -------------------------------------------------------
    print("\n[4] 并发（用户开多个窗口并行干活）")
    N = 12
    before = 0
    if os.path.isdir(tdir):
        for fn in os.listdir(tdir):
            if fn.endswith(".jsonl"):
                with io.open(os.path.join(tdir, fn), encoding="utf-8") as f:
                    before += len([x for x in f if x.strip()])
    procs = []
    for i in range(N):
        data = json.dumps({"hook_event_name": "Stop", "session_id": "conc%d" % i,
                           "last_assistant_message": "no header"}, ensure_ascii=False).encode("utf-8")
        procs.append(subprocess.Popen(argv, stdin=subprocess.PIPE,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        procs[-1].stdin.write(data)
        procs[-1].stdin.close()
    for p in procs:
        p.wait(timeout=120)
    time.sleep(0.6)
    lines, bad = [], 0
    for fn in os.listdir(tdir):
        if fn.endswith(".jsonl"):
            with io.open(os.path.join(tdir, fn), encoding="utf-8") as f:
                for ln in f:
                    if not ln.strip():
                        continue
                    lines.append(ln)
                    try:
                        json.loads(ln)
                    except ValueError:
                        bad += 1
    check("%d 个并发写入后每行仍是合法 JSON" % N, bad == 0, "%d 行损坏" % bad, note="0 损坏")
    check("并发写入一条都没丢", len(lines) - before >= N,
          "新增 %d 行（期望 >= %d）" % (len(lines) - before, N),
          note="新增 %d 行" % (len(lines) - before))

    # ---- 5. 长期增长：这才是真正的压测目标 -----------------------------------
    print("\n[5] 长期增长（装上以后用三个月会怎样）")
    per_line = 0
    if lines:
        per_line = sum(len(x.encode("utf-8")) for x in lines) / float(len(lines))
    # 保守估计：每天 200 次触发（重度使用），一年
    year_mb = per_line * 200 * 365 / 1024.0 / 1024.0
    print("     每行约 %d 字节，按每天 200 次触发算，一年约 %.1f MB" % (per_line, year_mb))

    n_state = len(os.listdir(sdir)) if os.path.isdir(sdir) else 0
    print("     .state 文件数：%d（每个会话一个）" % n_state)

    with io.open(os.path.join(hook_dir, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    keep = int(cfg["traces"]["retain_days"])
    keep_s = int(cfg["traces"]["state_retain_days"])

    # ⛔ 判据是「真的删了」，不是「代码里出现过 retain_days 这个词」。
    #    源码里有那个词和它真的会执行，是两件事——而这条压测存在的理由，
    #    正是发现配置写了 90 天却没有任何代码读它。
    #    所以造几个真的过期文件，跑一次 SessionStart，看它们还在不在。
    old_trace = os.path.join(tdir, "2020-01-01.jsonl")
    with io.open(old_trace, "w", encoding="utf-8") as f:
        f.write('{"rule":"OLD","gate":"x","action":"block"}\n')
    fresh_trace = os.path.join(tdir, time.strftime("%Y-%m-%d") + ".jsonl")
    old_state = os.path.join(sdir, "dead_session.json")
    if not os.path.isdir(sdir):
        os.makedirs(sdir)
    with io.open(old_state, "w", encoding="utf-8") as f:
        f.write("{}")
    ancient = time.time() - (max(keep, keep_s) + 30) * 86400
    os.utime(old_trace, (ancient, ancient))
    os.utime(old_state, (ancient, ancient))

    call(argv, {"hook_event_name": "SessionStart", "session_id": "prune1",
                "startup_type": "startup"})

    check("过期流水被清掉（config 写 %d 天，就真的删）" % keep,
          not os.path.isfile(old_trace), "2020-01-01.jsonl 还在")
    check("死会话的计数文件被清掉（%d 天）" % keep_s,
          not os.path.isfile(old_state), "dead_session.json 还在")
    # 反向断言：别把今天的也删了。只验「删掉了旧的」的话，
    # 一个把整个目录清空的实现同样能过。
    check("今天的流水没被误删（反向）", os.path.isfile(fresh_trace),
          "今天的 jsonl 不见了 —— 清理下手太狠")
    # 删东西要留痕，否则下次有人问「我那天的记录呢」谁也答不上来
    pruned_logged = False
    if os.path.isfile(fresh_trace):
        with io.open(fresh_trace, encoding="utf-8") as f:
            for ln in f:
                try:
                    if json.loads(ln).get("action") == "prune":
                        pruned_logged = True
                except ValueError:
                    pass
    check("清理动作本身留了痕", pruned_logged, "traces 里没有 action=prune")

    shutil.rmtree(work, ignore_errors=True)

    print("\n" + "=" * 66)
    failed = [n for n, ok in rows if not ok]
    if failed:
        print("[FAIL] %d/%d 条不过：%s" % (len(failed), len(rows), ", ".join(failed)))
        sys.exit(1)
    print("[OK] L0 压测 %d 条全过" % len(rows))
    sys.exit(0)


if __name__ == "__main__":
    main()
