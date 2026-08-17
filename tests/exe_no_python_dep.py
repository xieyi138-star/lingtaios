# -*- coding: utf-8 -*-
"""守：打包态发给用户的指令里，不许出现「跑 python」这类他机器上可能没有的命令。

为什么要有它
------------
`_run_generator` 里白纸黑字写着「零依赖意味着不能去找系统 Python：用户机器上
可能根本没有」——exe 因此改成进程内 runpy 跑生成器。**可发给用户的说明书里
却写着 `跑 python -X utf8 状态生成器.py`。** 产品亲手绕开的依赖，转头写进了
用户指令，等于让对方的 AI 去执行一条他跑不了的命令。

这跟「报错叫人去跑他根本没有的 install.py」是同一类错，那次已经付过一次代价。
光把文案改对不够——改对了没有东西守着，下一窗随手加一句又回去了。所以有这条。

另外顺带验 `--regen` 真能跑：文案里给用户的那条命令，必须真实存在且真的重算了。
写了替代方案不实现，跟没改一样。

⛔ 全程 --roots-file 沙盒 + 临时目录，不碰本机真源。
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
_CAND = [os.path.join(BC, d, "lingtaios.exe") for d in ("dist", "release_pkg")]
EXE = next((p for p in _CAND if os.path.isfile(p)), None)
DN = subprocess.DEVNULL
PORT = 8765


def sh(c):
    r = subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (r.stdout or b"").decode("mbcs", errors="replace")


def killport():
    for ln in sh("netstat -ano -p TCP").splitlines():
        p = ln.split()
        if len(p) >= 5 and p[0] == "TCP" and p[3] == "LISTENING" and p[1].endswith(":%d" % PORT):
            sh("taskkill /F /PID %s /T" % p[4])
    time.sleep(1.5)


def up(timeout=0.4):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        s.close()


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
    if EXE is None:
        print("[SKIP] 没有打好的 exe（dist\\ 和 release_pkg\\ 都没有）——这条只验打包态")
        return 3

    killport()
    work = tempfile.mkdtemp(prefix="nopy_")
    home = os.path.join(work, "home")
    proj = os.path.join(home, "probe-proj")
    os.makedirs(proj)
    rf = os.path.join(work, "roots.json")
    with io.open(rf, "w", encoding="utf-8") as f:
        json.dump({"machine_id": "NOPY", "setup_done": True,
                   "roots": {"NEXUS": None, "D": None, "HOME": home}},
                  f, ensure_ascii=False)

    results = []
    proc = None
    try:
        proc = subprocess.Popen([EXE, "--no-browser", "--roots-file", rf],
                                cwd=os.path.dirname(EXE), stdout=DN, stderr=DN)
        for _ in range(150):
            if up():
                break
            time.sleep(0.4)
        if not up():
            print("[FAIL] exe 起不来")
            return 1

        st, d = post("api/install_organs", {"path": proj})
        results.append(("装出六器官（HTTP %s）" % st, st == 200 and d.get("ok")))

        st, d = post("api/project_detail", {"path": proj})
        # ⛔ api_project_detail 的返回是**平铺**的，没有 detail 这一层。
        #    第一版这里写了 d.get("detail", {})，取到空串——而空串里当然「没有 python」，
        #    于是那条断言真空绿。下面那条反向断言就是为了照出这种空过，它第一次跑就照出来了。
        det = d.get("detail") or d
        # ⛔ resume 是**字符串**（dashboard.py: detail["resume"] = "\n".join(steps)）。
        #    第一版这里无条件 "\n".join(...)，把字符串按字符拆开又拼回去——
        #    每一「行」只剩一个字，`"python" in ln` 永远为假、`"--regen" in resume`
        #    也被插进去的换行切断。又是一次真空绿，又是被下面那条反向断言照出来的。
        raw = det.get("resume")
        resume = "\n".join(raw) if isinstance(raw, list) else (raw or "")
        # 光看长度不够：拆散的字符串照样很长。认一个只有真内容才有的锚点。
        results.append(("拿到了真的「继续做」指令（%d 字，含项目路径）" % len(resume),
                        st == 200 and len(resume) > 200 and proj in resume))
        bad = [ln for ln in resume.splitlines() if "python" in ln.lower()]
        results.append(("「继续做」指令里没有 python 命令" +
                        ("" if not bad else "（实际：%s）" % bad[0][:90]), st == 200 and not bad))
        # 反过来也要验：它得真给出一条能跑的替代命令，否则「没有 python」可以靠什么都不说达成
        results.append(("而且给了 --regen 或界面按钮这条活路",
                        ("--regen" in resume) or ("重算状态" in resume)))

        # 通用文案（设置 → 换机/我的文件 里那份）同样不许出现 python 命令，
        # 也不许再混进 `brain\...` 这种没有根的相对路径——那是开不了工的东西。
        st, t = post("api/templates", {})
        op = (t or {}).get("open", "")
        results.append(("拿到了通用文案（%d 字）" % len(op), st == 200 and len(op) > 40))
        results.append(("通用文案里没有 python 命令", "python" not in op.lower()))
        results.append(("通用文案里没有没根的 brain\\ 相对路径",
                        "brain\\01_" not in op and "brain\\05_" not in op))
    finally:
        if proc:
            proc.terminate()
            time.sleep(1.0)
        killport()

    # --regen 必须真的跑得动、真的重算（文案里给用户的命令，不能是空头支票）
    state = os.path.join(proj, "brain", "02_状态.md")
    before = os.path.getmtime(state) if os.path.isfile(state) else 0
    time.sleep(1.1)                      # mtime 分辨率，别让"没变"和"没跑"长得一样
    r = subprocess.run([EXE, "--regen", proj], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=180)
    out = (r.stdout or b"").decode("utf-8", errors="replace")
    after = os.path.getmtime(state) if os.path.isfile(state) else 0
    results.append(("exe --regen 退出 0（实际 %d）%s" % (
        r.returncode, "" if r.returncode == 0 else "：" + out[-120:]), r.returncode == 0))
    results.append(("--regen 真的重写了 02_状态.md（mtime 前 %.0f 后 %.0f）" % (before, after),
                    after > before))
    # 项目根目录也认（用户不一定知道要指到 brain\）
    r2 = subprocess.run([EXE, "--regen", os.path.join(proj, "brain")],
                        stdout=DN, stderr=DN, timeout=180)
    results.append(("--regen 给 brain 目录也认（实际 %d）" % r2.returncode, r2.returncode == 0))

    shutil.rmtree(work, ignore_errors=True)
    for name, ok in results:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
    bad = [n for n, o in results if not o]
    print("\n%s" % ("ALL PASSED" if not bad else "SOME FAILED"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
