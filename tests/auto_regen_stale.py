# -*- coding: utf-8 -*-
"""守：项目状态旧了，驾驶舱扫描时会自己重算——这是「永不脱节」的兜底层。

为什么要有它
------------
上一窗干完活、中间隔了几天、新窗口接手：**用户根本不知道 AI 上次做到哪**，
更不会记得先去点「重算状态」。他一打开驾驶舱看到的必须是真的，不是几天前的快照。

创始人真开工时就撞过：项目卡上写着「状态 1 天前」、详情页按钮就在旁边，
但他复制的是「继续做」指令、不是界面，从头到尾没看见那个按钮。

三层各堵一个洞，这条只守最底下那层：
  · 本层        —— 开了驾驶舱但什么都没点
  · 指令第 1 步 —— 直接复制去新窗口、没回驾驶舱
  · 详情页按钮 —— 想手动确认一次

两个方向都要验，缺一条这层网就是漏的：
  · 旧的必须被算（否则脱节照旧）
  · 新的必须跳过（否则每次刷页面都重算一遍所有项目，慢且吵）
⛔ 全程 --roots-file 沙盒 + 临时项目，不碰本机任何真项目。
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
PY, DN, PORT = sys.executable, subprocess.DEVNULL, 8765


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
        "http://127.0.0.1:%d/data.json" % PORT, timeout=60).read().decode("utf-8"))


def post(path, payload):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/%s" % (PORT, path),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def state_at(sj):
    with io.open(sj, encoding="utf-8") as f:
        return json.load(f).get("at")


def main():
    kill()
    sand = tempfile.mkdtemp(prefix="autoregen_")
    home = os.path.join(sand, "home")
    ws = os.path.join(sand, "work")
    proj = os.path.join(ws, "p-stale")
    os.makedirs(proj)
    io.open(os.path.join(proj, "README.md"), "w", encoding="utf-8").write("# p\n")
    os.makedirs(home)
    rf = os.path.join(sand, "roots.json")

    results = []
    proc = None
    try:
        # 第一段：用演练根起服务，把项目装上六器官（会顺手生成一次状态）
        with io.open(rf, "w", encoding="utf-8") as f:
            json.dump({"machine_id": "AUTOREGEN", "setup_done": True,
                       "roots": {"NEXUS": None, "D": None, "HOME": home},
                       "_workspaces": [ws]}, f, ensure_ascii=False)
        proc = subprocess.Popen([PY, "-X", "utf8", "dashboard.py", "--no-browser",
                                 "--roots-file", rf], cwd=BC, stdout=DN, stderr=DN)
        for _ in range(80):
            if up():
                break
            time.sleep(0.4)
        if not up():
            print("[FAIL] 服务没起来")
            return 1
        st, d = post("api/install_organs", {"path": proj})
        results.append(("装出六器官（HTTP %s）" % st, st == 200 and d.get("ok")))
        sj = os.path.join(proj, "brain", "02_状态.json")
        results.append(("装完就有状态", os.path.isfile(sj)))
        fresh_at = state_at(sj)

        # ── 方向一：状态是新的 → 扫描时**不许**重算 ──────────────────────
        post("api/refresh", {})
        results.append(("新的状态不被重算（at 没变：%s）" % fresh_at,
                        state_at(sj) == fresh_at))
    finally:
        if proc:
            proc.terminate()
            time.sleep(1.0)
        kill()

    # ── 方向二：把状态改成 3 天前 → 重启后扫描必须自己算回来 ─────────────
    # ⛔ 演练态不碰真项目，所以这一段改用**真 roots**：把临时项目登记成 _projects，
    #    这样它就是「一个真项目」，扫描时该被自动重算。跑完把登记撤掉。
    old = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3 * 86400))
    with io.open(sj, encoding="utf-8") as f:
        js = json.load(f)
    js["at"] = old
    with io.open(sj, "w", encoding="utf-8") as f:
        json.dump(js, f, ensure_ascii=False)
    results.append(("把状态改成 3 天前（%s）" % old, state_at(sj) == old))

    real_rf = os.path.join(BC, "roots.json")
    backup = os.path.join(sand, "roots_backup.json")
    shutil.copyfile(real_rf, backup)
    try:
        with io.open(real_rf, encoding="utf-8") as f:
            rj = json.load(f)
        # ⛔ roots.json 里的键是 `projects`；`_projects` 是 load_roots 映射之后的内部名。
        #    第一版写成 _projects，等于没登记——项目根本没被发现，那条断言只是在
        #    验一个不存在的项目「没被重算」，红得莫名其妙。写配置前先看它怎么被读的。
        rj["projects"] = list(rj.get("projects") or []) + [proj]
        with io.open(real_rf, "w", encoding="utf-8") as f:
            json.dump(rj, f, ensure_ascii=False, indent=2)
        proc = subprocess.Popen([PY, "-X", "utf8", "dashboard.py", "--no-browser"],
                                cwd=BC, stdout=DN, stderr=DN)
        for _ in range(80):
            if up():
                break
            time.sleep(0.4)
        d = data() if up() else {}
        now_at = state_at(sj)
        results.append(("旧状态被扫描时自动重算（%s -> %s）" % (old, now_at), now_at != old))
        p = [x for x in d.get("projects", []) if x["name"] == "p-stale"]
        results.append(("而且它在项目列表里显示为 0 天前",
                        bool(p) and p[0].get("state_age_days") == 0))
    finally:
        if proc:
            proc.terminate()
            time.sleep(1.0)
        kill()
        shutil.copyfile(backup, real_rf)          # 真 roots.json 还原
        restored = io.open(real_rf, "rb").read() == io.open(backup, "rb").read()
        results.append(("跑完真 roots.json 逐字节还原", restored))
        # ⛔ 还原配置**还不够**：临时项目被登记的那段时间里，真 site\data.json
        #    已经按 23 个项目重新生成过了。只还原 roots.json 就走，留下的是一份
        #    多一个项目的产物——实测直接把 wizard_v3_e2e / dedup_back_e2e 干红了
        #    （它们比对真 data.json 的项目数）。
        #    「演练不许碰真源」要连**产物**一起算，堵一半等于没堵。
        subprocess.run([PY, "-X", "utf8", "dashboard.py", "--build-only"],
                       cwd=BC, stdout=DN, stderr=DN, timeout=180)
        try:
            with io.open(os.path.join(BC, "site", "data.json"), encoding="utf-8") as f:
                names = [x["name"] for x in json.load(f)["projects"]]
            results.append(("真 data.json 也已重建，临时项目没留在里面（%d 个）" % len(names),
                            "p-stale" not in names))
        except (OSError, ValueError) as e:
            results.append(("真 data.json 重建后可读（%s）" % e, False))
        shutil.rmtree(sand, ignore_errors=True)

    for name, ok in results:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
    bad = [n for n, o in results if not o]
    print("\n%s" % ("ALL PASSED" if not bad else "SOME FAILED"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
