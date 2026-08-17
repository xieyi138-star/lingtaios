# -*- coding: utf-8 -*-
"""量具跑不了的时候，**绝不许把「取不到」当成新状态写下去**。

为什么要有它
------------
2026-08-17 实测：`lingtaios.exe --regen` 跑 IPGuard，exe 里打包的 Python 没有
sqlite3，11 个探针全抛 ModuleNotFoundError，生成器照样把这份「全是取数失败」
写进了 02_状态.md —— 一份 10 个探针全绿的真状态被一堆红覆盖，**旧数再也拿不回来**。
「取数失败必须出声」是对的，但出声 ≠ 把失败当成新状态存档。

这条守两件事，缺一不可：
  1. 缺模块时先借本机现成的 Python 跑一趟（装了就用，这才是根治）；
  2. 连本机 Python 也救不了 → 退出码 3、**一个字节都不许写**。

⛔ 只验第 2 条不够：第 1 条坏掉的表现是「状态永远停在旧的」，
   而它长得和「没人点重算」一模一样，静默。所以正反两面都要断言。
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD_MD = u"# 状态\n\n> 生成于 2001-01-01 00:00:00\n\n| 名 | 值 |\n|---|---|\n| 真数 | 42 |\n"
GOOD_JSON = {"at": "2001-01-01 00:00:00", "values": {u"真数": 42}, "alarms": [],
             "high_water": {}}


def _exe():
    for d in ("dist", "release_pkg"):
        p = os.path.join(BC, d, "lingtaios.exe")
        if os.path.isfile(p):
            return p
    return None


def md5(p):
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def _mk(tmp, probe_body, probes):
    """造一个最小项目：brain/ + 一个探针模块 + 一份「上一次的好状态」。"""
    brain = os.path.join(tmp, "brain")
    os.makedirs(brain)
    with io.open(os.path.join(brain, "probe_x.py"), "w", encoding="utf-8") as f:
        f.write(probe_body)
    with io.open(os.path.join(brain, u"状态源.json"), "w", encoding="utf-8") as f:
        json.dump({"project": "t", "root": "..", "probes": probes}, f, ensure_ascii=False)
    with io.open(os.path.join(brain, u"02_状态.md"), "w", encoding="utf-8") as f:
        f.write(GOOD_MD)
    with io.open(os.path.join(brain, u"02_状态.json"), "w", encoding="utf-8") as f:
        json.dump(GOOD_JSON, f, ensure_ascii=False)
    return brain


def _snap(brain):
    return {n: md5(os.path.join(brain, n)) for n in (u"02_状态.md", u"02_状态.json")}


def main():
    exe = _exe()
    if not exe:
        print(u"[跳过] 找不到 lingtaios.exe——这条只验打包态，源码态跑不出这个坑")
        return 3
    fails = []
    tmp = tempfile.mkdtemp(prefix="regen_broken_")
    try:
        # ── 反面：探针 import 一个哪儿都没有的模块 → 谁也救不了 → 必须拒写
        b1 = _mk(os.path.join(tmp, "a"),
                 u"import zzz_no_such_module_lingtai\nROWS = [1, 2, 3]\n",
                 [{"name": u"救不了的", "type": "py_attr_len",
                   "module": "brain/probe_x.py", "attr": "ROWS"}])
        before = _snap(b1)
        r = subprocess.run([exe, "--regen", b1], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 3:
            fails.append(u"救不了时退出码该是 3，实得 %s\n%s" % (r.returncode, out[-600:]))
        if _snap(b1) != before:
            fails.append(u"⛔ 量具坏了却把状态覆盖了——这正是那个坑")
        if u"没有重算" not in out:
            fails.append(u"没说清「没有重算」，人会以为数据出事了：%s" % out[-300:])
        print(u"  救不了 → 退出码 %s，状态 %s" %
              (r.returncode, u"原样" if _snap(b1) == before else u"**被覆盖**"))

        # ── 正面：探针只用标准库里 exe 没打包的模块（sqlite3）→ 借本机 Python 跑通
        b2 = _mk(os.path.join(tmp, "b"),
                 u"import sqlite3\nROWS = [1, 2, 3, 4, 5]\n",
                 [{"name": u"要sqlite3的", "type": "py_attr_len",
                   "module": "brain/probe_x.py", "attr": "ROWS"}])
        r2 = subprocess.run([exe, "--regen", b2], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
        out2 = (r2.stdout or "") + (r2.stderr or "")
        with io.open(os.path.join(b2, u"02_状态.json"), encoding="utf-8") as f:
            got = json.load(f)
        if got.get("values", {}).get(u"要sqlite3的") != 5:
            fails.append(u"exe 缺 sqlite3 时没能借本机 Python 救回来，实得 %s\n%s"
                         % (got.get("values"), out2[-600:]))
        print(u"  借本机 Python → 读到 %s（期望 5）" % got.get("values", {}).get(u"要sqlite3的"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(u"[FAIL] %d 条" % len(fails))
        for x in fails:
            print(u"  - " + x)
        return 1
    print(u"[OK] 量具坏了拒写、能救则救——两面都对")
    return 0


if __name__ == "__main__":
    sys.exit(main())
