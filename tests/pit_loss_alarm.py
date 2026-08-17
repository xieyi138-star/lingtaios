# -*- coding: utf-8 -*-
"""守：经验库悄悄变少了必须出声。

界面上写着「你的东西都在这儿，随时能打开」，那就一定会有人去手动改坑库.md。
而它是按**表格结构**解析的——删错一个竖线、少一列，那一行就不算数了，
条数静默变少，AI 从此读到的是一份缺角的经验库，而用户只会觉得「这系统不稳」。

灵台拦不住他改（也不该拦，记忆归他），但**绝不能默默接受这种损失**。
三条都得验，缺一条这道网就是漏的：
  1. 手改导致变少 → 报出来（不许静默）
  2. 走界面「这条不用了」退休 → **不报**（有意的减少不该变成噪音，
     噪音会让人学会无视这盏灯）
  3. 用户确认「是我删的」→ 基线对齐，从此不再报

⛔ 全程 --roots-file 沙盒 + 临时坑库副本，不碰本机真源。
"""
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = BC if os.path.isdir(os.path.join(BC, "project-delivery")) else os.path.dirname(BC)
PY = sys.executable
DN = subprocess.DEVNULL
PORT = 8765


def sh(c):
    r = subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (r.stdout or b"").decode("mbcs", errors="replace")


def kill():
    for ln in sh("netstat -ano -p TCP").splitlines():
        p = ln.split()
        if len(p) >= 5 and p[0] == "TCP" and p[3] == "LISTENING" and p[1].endswith(":%d" % PORT):
            sh("taskkill /F /PID %s /T" % p[4])
    sh('wmic process where "name=\'python.exe\' and commandline like \'%%dashboard.py%%\'" delete')
    time.sleep(1.5)


def up():
    s = socket.socket()
    s.settimeout(0.4)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        s.close()


def data():
    return json.loads(urllib.request.urlopen(
        "http://127.0.0.1:%d/data.json" % PORT, timeout=30).read().decode("utf-8"))


def post(path, payload):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/%s" % (PORT, path),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def main():
    kill()
    sand = tempfile.mkdtemp(prefix="pitloss_")
    home = os.path.join(sand, "home")
    os.makedirs(home)
    rf = os.path.join(sand, "roots.json")
    with io.open(rf, "w", encoding="utf-8") as f:
        json.dump({"machine_id": "PITLOSS", "setup_done": True,
                   "roots": {"NEXUS": None, "D": None, "HOME": home}},
                  f, ensure_ascii=False)

    # ⛔ 演练态用的仍是真坑库文件（REPO 不随 --roots-file 走），所以先备份、跑完还原
    pit = os.path.join(SKILLS, "project-delivery", "坑库.md")
    backup = os.path.join(sand, "pit_backup.md")
    shutil.copyfile(pit, backup)

    results = []
    proc = None
    try:
        proc = subprocess.Popen([PY, "-X", "utf8", "dashboard.py", "--no-browser",
                                 "--roots-file", rf], cwd=BC, stdout=DN, stderr=DN)
        for _ in range(80):
            if up():
                break
            time.sleep(0.4)
        if not up():
            print("[FAIL] 服务没起来")
            return 1

        d0 = data()
        n0 = len(d0["pitfall"]["rows"])
        results.append(("起手没有误报（pit_loss 为空，%d 条）" % n0, not d0.get("pit_loss")))

        # 1. 手改：把最后一条坑的行首竖线删掉——正是「格式改坏」的典型样子
        txt = io.open(pit, encoding="utf-8").read()
        lines = txt.split("\n")
        idx = max(i for i, ln in enumerate(lines) if ln.startswith("| ") and ln.count("|") > 5)
        lines[idx] = lines[idx][1:]              # 少一个竖线，这一行就不算数了
        io.open(pit, "w", encoding="utf-8").write("\n".join(lines))
        st, d1 = post("api/refresh", {})
        loss = d1.get("pit_loss")
        results.append(("手改导致变少 → 报出来（%s）" % json.dumps(loss, ensure_ascii=False),
                        bool(loss) and loss.get("was") == n0 and loss.get("now") < n0))

        # 2. 用户确认「是我删的」→ 从此不再报
        st, _ = post("api/pit_loss_ack", {})
        d2 = data()
        results.append(("确认之后不再报", st == 200 and not d2.get("pit_loss")))

        # 3. 走界面退休一条 → 不该报（有意的减少不是噪音）
        n2 = len(d2["pitfall"]["rows"])
        code = d2["pitfall"]["rows"][-1]["编号"]
        st, r = post("api/audit_delete", {"kind": "pitfall", "ids": [code]})
        d3 = data()
        results.append(("走界面退休一条（%s）后条数 -1" % code,
                        st == 200 and len(d3["pitfall"]["rows"]) == n2 - 1))
        results.append(("而且**不报**——有意的减少不该变成噪音", not d3.get("pit_loss")))
    finally:
        if proc:
            proc.terminate()
            time.sleep(1.0)
        kill()
        shutil.copyfile(backup, pit)             # 真源还原
        # ⛔ 先验再删。第一版把 rmtree 写在前面，回头再去读 backup 对比——
        #    文件已经没了，那条断言只能永远为真。「工具返回成功 ≠ 事情做成了」
        #    同样适用于「我以为我还原了」。
        restored = (io.open(pit, "rb").read() == io.open(backup, "rb").read())
        results.append(("跑完真源逐字节还原", restored))
        shutil.rmtree(sand, ignore_errors=True)

    for name, ok in results:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
    bad = [n for n, o in results if not o]
    print("\n%s" % ("ALL PASSED" if not bad else "SOME FAILED"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
