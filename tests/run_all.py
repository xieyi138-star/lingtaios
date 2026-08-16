# -*- coding: utf-8 -*-
"""全量回归 · 一条命令跑完并自动收尾

为什么要有它
------------
以前全量回归是 README 里 14 条命令，靠人一条条敲。两个后果：
  · 漏跑不会有人知道——没跑过的脚本和跑绿的脚本，在人脑里长得一样；
  · **每个脚本跑完都会清掉 8765 上的服务**，靠人记得手动起回来。上一窗
    就是忘了这一步，浏览器里报 TypeError: Failed to fetch，误报了一次
    「产品挂了」。红线写在 HANDOFF 里，但没有任何东西执行它。
这里把「跑完起回服务」做成脚本的 finally，不再依赖谁记得。

用法
----
    python -X utf8 tests\\run_all.py               # 全量（跳过会弹窗的）
    python -X utf8 tests\\run_all.py --with-dialogs  # 连原生对话框的一起跑（会弹窗，别走开）
    python -X utf8 tests\\run_all.py --no-restart    # 跑完不起服务（调试用）
"""
import argparse
import os
import socket
import subprocess
import sys
import time

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(BC, "tests")
PY = sys.executable

# 会杀 8765 的常规脚本，按依赖顺序排（重的放前面，快的放后面）
SUITE = [
    "repo_parity.py",        # 两仓一致性：不动服务，先跑掉
    "soul_manifest.py",
    "two_form_parity.py",
    "stress_a.py",
    "stress_b.py",
    "destructive_probe.py",
    "project_mgmt_stress.py",
    "exe_mgmt_check.py",
    "no_pollute_test.py",
    "workspace_e2e.py",
    "finder_e2e.py",
    "wizard_v3_e2e.py",
    "dedup_back_e2e.py",
    "brand_check.py",
    "nav_check.py",
]
# ⛔ 这两个会弹原生文件夹对话框，挡在屏幕上；默认不跑，要跑得人在旁边
DIALOG = ["native_pick_e2e.py", "pick_lock_test.py"]
# 需要服务活着，必须放在起服务之后
NEEDS_LIVE = ["detail_live_check.py"]


def _exe():
    for d in ("dist", "release_pkg"):
        p = os.path.join(BC, d, "lingtaios.exe")
        if os.path.isfile(p):
            return p
    return None


def _up(port=8765, timeout=1.0):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def start_service():
    exe = _exe()
    if not exe:
        print("[!!] 找不到 lingtaios.exe（dist\\ 和 release_pkg\\ 都没有），服务起不回来")
        return False
    d = os.path.dirname(exe)
    subprocess.Popen([exe], cwd=d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        time.sleep(0.5)
        if _up():
            return True
    return False


def run(script, label=None):
    p = os.path.join(TESTS, script)
    if not os.path.isfile(p):
        return (script, None, "脚本不存在")
    t0 = time.time()
    r = subprocess.run([PY, "-X", "utf8", p], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    out = (r.stdout or b"").decode("utf-8", errors="replace")
    tail = [ln for ln in out.strip().splitlines() if ln.strip()]
    last = tail[-1] if tail else ""
    # 有的脚本自己不设退出码，靠末行文案表态——两个都看，任一为红就算红
    red = (r.returncode != 0) or ("SOME FAILED" in out) or ("[FAIL]" in out) \
        or ("内容不同 0 件" not in out and "soul_manifest" in script)
    print("  %-24s %s  (%.0fs)  %s" % (script, "红" if red else "绿", time.time() - t0, last[:70]))
    return (script, not red, last)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-dialogs", action="store_true")
    ap.add_argument("--no-restart", action="store_true")
    args = ap.parse_args()

    results = []
    try:
        print("=== 常规回归（每个跑完都会清掉 8765）===")
        for s in SUITE:
            results.append(run(s))
        if args.with_dialogs:
            print("=== 原生对话框（会弹窗，别动鼠标）===")
            for s in DIALOG:
                results.append(run(s))
        else:
            print("=== 跳过 %s —— 会弹原生对话框，要跑加 --with-dialogs ===" % ", ".join(DIALOG))

        if not args.no_restart:
            print("=== 起回服务，再跑需要活服务的 ===")
            ok = start_service()
            print("  服务 %s" % ("已起来" if ok else "没起来 [!!]"))
            if ok:
                for s in NEEDS_LIVE:
                    results.append(run(s))
            else:
                print("  跳过 %s（服务没起来）" % ", ".join(NEEDS_LIVE))
    finally:
        # ⛔ 无论上面怎么炸，服务都必须回到跑着的状态，否则用户浏览器里
        #    那个页面会报 TypeError: Failed to fetch，看起来像产品挂了。
        if not args.no_restart and not _up():
            print("=== 收尾：服务不在，起回来 ===")
            print("  服务 %s" % ("已起来" if start_service() else "没起来 [!!] 手动跑 dist\\lingtaios.exe"))

    red = [s for s, ok, _ in results if ok is False]
    skipped = [s for s, ok, _ in results if ok is None]
    print("\n" + "=" * 60)
    print("跑了 %d 个：绿 %d / 红 %d / 跳过 %d" %
          (len(results), len(results) - len(red) - len(skipped), len(red), len(skipped)))
    if red:
        print("红的：%s" % ", ".join(red))
    print("服务状态：%s" % ("UP" if _up() else "DOWN [!!]"))
    sys.exit(1 if red else 0)


if __name__ == "__main__":
    main()
