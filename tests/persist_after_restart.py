# -*- coding: utf-8 -*-
"""坑库 R4 的执行者：写入 → **重启进程** → 复查仍在。

R4 的失效判据写的就是「回归里有写入→重启进程→复查仍在的持久化用例，只验返回码不算」。
写了判据不实现，判据就是空头支票——所以有这个脚本。

R4 原案：打包态曾把 sys._MEIPASS（每次启动新建的临时解压目录）当数据目录。
用户点「记坑」，接口返 200、界面条数 38→39，看起来完全正常；
进程一退出临时目录被清理，那条坑就没了，而且悄无声息。
只验返回码的测试**永远发现不了这个**——返回码从头到尾都是 200。

⛔ 全程不碰主源码真源：exe 复制到临时目录跑，首跑会在那儿落一份自己的
   project-delivery，测完整个目录删掉。脚本同时校验真源 md5 全程不变。
"""
import hashlib
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
_CAND = [os.path.join(BC, d, "lingtaios.exe") for d in ("dist", "release_pkg")]
EXE = next((p for p in _CAND if os.path.isfile(p)), _CAND[0])
SKILLS = BC if os.path.isdir(os.path.join(BC, "project-delivery")) else os.path.dirname(BC)
TRUE_PIT = os.path.join(SKILLS, "project-delivery", "坑库.md")
PORT = 8765
DN = subprocess.DEVNULL
MARK = "PERSIST-REGRESSION-PROBE"


def md5(p):
    try:
        return hashlib.md5(io.open(p, "rb").read()).hexdigest()[:8]
    except OSError:
        return None


def sh(c):
    r = subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (r.stdout or b"").decode("mbcs", errors="replace")


def kill_port():
    for ln in sh("netstat -ano -p TCP").splitlines():
        if (":%d " % PORT) in ln and "LISTENING" in ln:
            pid = ln.split()[-1]
            if pid.isdigit() and pid != "0":
                sh("taskkill /F /PID %s" % pid)
    time.sleep(1.5)


def up(timeout=1.0):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def start(workdir, exe):
    subprocess.Popen([exe, "--no-browser"], cwd=workdir, stdout=DN, stderr=DN)
    for _ in range(40):
        time.sleep(0.5)
        if up():
            return True
    return False


def post(path, obj):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path),
                                 data=json.dumps(obj).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))


def rows():
    d = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/data.json" % PORT,
                                          timeout=15).read().decode("utf-8"))
    return d["pitfall"]["rows"]


def main():
    if not os.path.isfile(EXE):
        print("[SKIP] 找不到 lingtaios.exe，先打包再跑")
        return 0

    before_true = md5(TRUE_PIT)
    work = tempfile.mkdtemp(prefix="persist_")
    exe = os.path.join(work, os.path.basename(EXE))
    shutil.copyfile(EXE, exe)
    results = []
    try:
        kill_port()
        if not start(work, exe):
            print("[FAIL] exe 在临时目录里起不来")
            return 1

        seeded = os.path.isdir(os.path.join(work, "project-delivery"))
        results.append(("首跑把方法论真源落到 exe 旁边（不是临时解压目录）", seeded))

        n0 = len(rows())
        r = post("/api/add_pitfall", {
            "section": "工具坑", "pit": MARK, "fix": "probe",
            "source": "persist_after_restart.py", "invalid_when": "probe"})
        results.append(("记一条坑接口返回 ok", bool(r.get("ok"))))
        n1 = len(rows())
        results.append(("界面条数 +1（%d→%d）" % (n0, n1), n1 == n0 + 1))

        # ← 这一步是全部意义所在：只验上面几条，坏掉的旧实现也全绿
        kill_port()
        if not start(work, exe):
            print("[FAIL] 重启后 exe 起不来")
            return 1

        n2 = len(rows())
        survived = any(MARK in (x.get("一句话坑") or "") for x in rows())
        results.append(("**重启后那条坑还在**（%d→%d）" % (n1, n2), survived and n2 == n1))

        code = [x["编号"] for x in rows() if MARK in (x.get("一句话坑") or "")]
        if code:
            post("/api/audit_delete", {"kind": "pitfall", "ids": code})
            results.append(("删得掉（汰有机制可用）",
                            not any(MARK in (x.get("一句话坑") or "") for x in rows())))
    finally:
        kill_port()
        shutil.rmtree(work, ignore_errors=True)

    results.append(("全程没碰主源码真源（md5 不变）", md5(TRUE_PIT) == before_true))

    for name, ok in results:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
    bad = [n for n, o in results if not o]
    print("\n%s" % ("ALL PASSED" if not bad else "SOME FAILED: %s" % "; ".join(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
