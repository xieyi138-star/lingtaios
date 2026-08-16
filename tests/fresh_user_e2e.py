# -*- coding: utf-8 -*-
"""全新用户第一次打开：一台**没有作者那套目录**的机器上，灵台能不能用起来。

为什么单开一条
--------------
本机测试全是在「有 C:\\nexus_local、有 22 个项目、roots 全绿」的环境下跑的，
而真实新用户是反过来的：没有 NEXUS 根、没有 D 盘业务目录、一个项目都没有。
这条路径此前**从没被验过**——首页会不会白屏、空状态有没有引导、能不能建出
第一个项目，全靠猜。有真实用户之后，这条比任何回归都靠前。

模拟方式：exe 复制到全新临时目录，喂一份「什么根都没有」的 roots.json
（走 --roots-file 沙盒，红线：演练不许碰真源），然后走完新用户的动作。
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
EXE = next((p for p in _CAND if os.path.isfile(p)), _CAND[0])
SKILLS = BC if os.path.isdir(os.path.join(BC, "project-delivery")) else os.path.dirname(BC)
TRUE_ROOTS = os.path.join(BC, "roots.json")
PORT = 8765
DN = subprocess.DEVNULL


def sh(c):
    r = subprocess.run(c, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (r.stdout or b"").decode("mbcs", errors="replace")


def kill():
    for ln in sh("netstat -ano -p TCP").splitlines():
        if (":%d " % PORT) in ln and "LISTENING" in ln:
            pid = ln.split()[-1]
            if pid.isdigit() and pid != "0":
                sh("taskkill /F /PID %s" % pid)
    time.sleep(1.5)


def up():
    s = socket.socket()
    s.settimeout(1.0)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def get(path):
    return urllib.request.urlopen("http://127.0.0.1:%d%s" % (PORT, path),
                                  timeout=20).read().decode("utf-8")


def post(path, obj):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path),
                                 data=json.dumps(obj).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))


def main():
    if not os.path.isfile(EXE):
        print("[SKIP] 找不到 lingtaios.exe，先打包")
        return 0

    before_roots = os.path.isfile(TRUE_ROOTS) and io.open(TRUE_ROOTS, "rb").read()
    work = tempfile.mkdtemp(prefix="freshuser_")
    exe = os.path.join(work, "lingtaios.exe")
    shutil.copyfile(EXE, exe)
    # 一台干净机器：没有 NEXUS 业务根，没有 D 盘目录，一个项目都没登记
    roots_file = os.path.join(work, "roots.json")
    io.open(roots_file, "w", encoding="utf-8").write(json.dumps({
        "machine_id": "FRESH-USER-PC",
        "roots": {"NEXUS": None, "D": None, "HOME": work},
        "setup_done": False,
    }, ensure_ascii=False, indent=2))

    results = []
    try:
        kill()
        subprocess.Popen([exe, "--no-browser", "--roots-file", roots_file],
                         cwd=work, stdout=DN, stderr=DN)
        ok = False
        for _ in range(40):
            time.sleep(0.5)
            if up():
                ok = True
                break
        results.append(("没有任何业务根，服务照样起得来", ok))
        if not ok:
            raise SystemExit(1)

        d = json.loads(get("/data.json"))
        results.append(("data.json 取得到，不是 500", True))
        results.append(("项目数为 0（新用户本来就没有）：实 %d" % len(d["projects"]),
                        len(d["projects"]) == 0))
        results.append(("方法论真源仍可读（坑库 %d 条）——它随 exe 落盘，不依赖用户目录"
                        % len(d["pitfall"]["rows"]), len(d["pitfall"]["rows"]) > 0))
        # 缺根不许静默：界面得说清楚哪个根没配
        rs = d.get("root_status") or {}
        results.append(("缺失的根有出声（root_status 里标了）", bool(rs)))

        html = get("/")
        results.append(("首页 HTML 渲染得出来，不是白屏（%d 字节）" % len(html), len(html) > 500))
        appjs = get("/app.js")
        results.append(("空项目库有引导文案，不是空白", "项目库还是空的" in appjs))

        # 不给 root_choice 必须明确报错，并把本机可用的选项列出来——
        # 曾经这里默认走 "nexus"，把作者机器的 C:\nexus_local 当所有人的默认落点。
        r0 = post("/api/create_project", {"name": "no-root-choice"})
        results.append(("不给落点时报错说得清（%s）" % (r0.get("error") or "")[:40],
                        not r0.get("ok") and "custom" in (r0.get("error") or "")))

        # 新用户的第一个真实动作：建一个项目。他机器上只有 HOME，界面会把它映射成 custom。
        r = post("/api/create_project", {
            "name": "my-first-project", "root_choice": "custom", "custom_path": work,
            "goals": [{"name": "跑通", "def": "能建出项目", "line": "1 个"}],
            "redlines": "不删用户文件"})
        proj = os.path.join(work, "my-first-project")
        results.append(("能建出第一个项目（%s）" % (r.get("error") or "ok"), bool(r.get("ok"))))
        organs = os.path.join(proj, "brain")
        n_organ = len([f for f in os.listdir(organs)]) if os.path.isdir(organs) else 0
        results.append(("六器官真的落到磁盘上了（%d 个文件）" % n_organ, n_organ >= 8))

        d2 = json.loads(get("/data.json"))
        results.append(("建完之后项目出现在列表里（%d 个）" % len(d2["projects"]),
                        len(d2["projects"]) >= 1))

        det = post("/api/project_detail", {"path": proj})
        resume = (det[1] if isinstance(det, list) else det).get("resume", "") \
            if isinstance(det, (list, dict)) else ""
        if isinstance(det, dict):
            resume = det.get("resume", "") or (det.get("detail") or {}).get("resume", "")
        results.append(("「继续做」指令生成得出来且指向用户自己的路径",
                        bool(resume) and work.lower() in resume.lower()))
    finally:
        kill()
        shutil.rmtree(work, ignore_errors=True)

    now = os.path.isfile(TRUE_ROOTS) and io.open(TRUE_ROOTS, "rb").read()
    results.append(("全程没碰真 roots.json", now == before_roots))

    for name, ok in results:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
    bad = [n for n, o in results if not o]
    print("\n%s" % ("ALL PASSED" if not bad else "SOME FAILED"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
