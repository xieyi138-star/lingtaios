# -*- coding: utf-8 -*-
"""解压到**中文+空格路径**下还能不能用。

中国用户十有八九会解压到「下载\\灵台 OS」这种目录：路径里既有中文又有空格。
Windows 上这两样单拎出来都是老坑（编码、引号、命令行传参），叠一起更是。
这条不通，前面所有验证都白做——所以单独一条，跑全量时一起跑。

⛔ 全程在系统临时目录下的中文子目录里，测完整个删掉；不碰真源。
"""
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
SRC_EXE = next((p for p in _CAND if os.path.isfile(p)), _CAND[0])
PORT, DN = 8765, subprocess.DEVNULL


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


def get(p):
    return urllib.request.urlopen("http://127.0.0.1:%d%s" % (PORT, p),
                                  timeout=20).read().decode("utf-8")


def post(p, o):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, p),
                                 data=json.dumps(o).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))


def main():
    if not os.path.isfile(SRC_EXE):
        print("[SKIP] 找不到 lingtaios.exe，先打包")
        return 0

    base = tempfile.mkdtemp(prefix="cnpath_")
    work = os.path.join(base, "灵台 测试 目录")     # 中文 + 空格，两样都占
    os.makedirs(work)
    exe = os.path.join(work, "lingtaios.exe")
    shutil.copyfile(SRC_EXE, exe)

    res = []
    try:
        r = subprocess.run([exe, "--selftest"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = (r.stdout or b"").decode("utf-8", errors="replace")
        res.append(("中文+空格路径下 --selftest 全过（%d 项，rc=%d）"
                    % (out.count("  ok "), r.returncode),
                    r.returncode == 0 and out.count("  ok ") >= 20))
        res.append(("出厂真源落得下来（project-delivery 在）",
                    os.path.isdir(os.path.join(work, "project-delivery"))))

        kill()
        subprocess.Popen([exe, "--no-browser"], cwd=work, stdout=DN, stderr=DN)
        ok = False
        for _ in range(40):
            time.sleep(0.5)
            if up():
                ok = True
                break
        res.append(("服务起得来", ok))
        if ok:
            d = json.loads(get("/data.json"))
            res.append(("data.json 正常（坑库 %d 条）" % len(d["pitfall"]["rows"]),
                        len(d["pitfall"]["rows"]) > 0))
            html = get("/")
            res.append(("首页不白屏（%d 字节）" % len(html), len(html) > 500))
            n0 = len(d["projects"])
            # 项目名也用中文——用户当然会这么起名
            rr = post("/api/create_project", {
                "name": "我的第一个项目", "root_choice": "custom", "custom_path": work,
                "goals": [{"name": "跑通", "def": "能建出来", "line": "1 个"}],
                "redlines": "不删文件"})
            res.append(("中文项目名建得出来（%s）" % (rr.get("error") or "ok"), bool(rr.get("ok"))))
            brain = os.path.join(work, "我的第一个项目", "brain")
            n = len(os.listdir(brain)) if os.path.isdir(brain) else 0
            res.append(("六器官落盘（%d 个文件）" % n, n >= 8))
            d2 = json.loads(get("/data.json"))
            res.append(("建完出现在列表里（%d → %d）" % (n0, len(d2["projects"])),
                        len(d2["projects"]) > n0))
    finally:
        kill()
        shutil.rmtree(base, ignore_errors=True)

    for n, o in res:
        print("[%s] %s" % ("PASS" if o else "FAIL", n))
    bad = [n for n, o in res if not o]
    print("\n%s" % ("ALL PASSED" if not bad else "SOME FAILED"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
