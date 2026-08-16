# -*- coding: utf-8 -*-
"""坑库 P23 的执行者：真 clone 一份，按用户文档第一条命令从头走一遍。

P23 的失效判据写的就是「clone 冒烟（装→跑→打包→自检）已进回归，未过不许发布」。
写了判据不实现，判据就是空头支票——所以有这个脚本。

P23 原案：主源码目录里 selftest 24/24、全量回归 16 项全绿、两仓 MD5 逐字节一致，
看起来无懈可击；真 clone 出来跑 install.py，12 项方法层真源全 [XX]、退出码 1，
系统根本装不上。原因是**所有路径在自己机器上碰巧都是对的**——写死的绝对路径指向
的正是本机，dirname(dirname(__file__)) 在主源码布局下算出来也正好对。
在开发目录里跑一百遍也照不出这类错，只有换一种布局才暴露。

四步（对应用户实际会走的路）：
  1. install.py            —— README 第一条命令，退出码必须 0、不能有 [XX]
  2. dashboard.py --selftest —— 源码态，README 给的另一条路
  3. pyinstaller lingtaios.spec —— 用户自己打包
  4. 打出来的 exe --selftest  —— 装出来的东西真能跑

⛔ 全程在临时目录里，--claude-dir 也指临时目录，不碰本机 ~/.claude。
⚠️ 它 clone 的是发布仓的 **HEAD**，不是工作区——所以验的是「别人现在 clone 会拿到什么」。
   这个语义才是对的（用户拿到的就是 HEAD），但意味着**改完要先 commit 再跑它**，
   否则你验的是上一版。第一次跑就被这条绊过一次。
"""
import os
import shutil
import subprocess
import sys
import tempfile

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = os.environ.get("LINGTAI_MIRROR") or r"D:\tmp\lingtaios-repo"
PY = sys.executable
DN = subprocess.DEVNULL
FULL = "--full" in sys.argv or os.environ.get("CLONE_SMOKE_FULL") == "1"


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode, (r.stdout or b"").decode("utf-8", errors="replace")


def main():
    if not os.path.isdir(os.path.join(MIRROR, ".git")):
        print("[SKIP] 没有发布仓（%s）——这条只在有发布仓的机器上跑得了。" % MIRROR)
        print("       换机或挪过位置设环境变量 LINGTAI_MIRROR。")
        return 0
    if shutil.which("git") is None:
        print("[SKIP] 没有 git，clone 不了")
        return 0

    work = tempfile.mkdtemp(prefix="clone_smoke_")
    repo = os.path.join(work, "clone")
    fake_claude = os.path.join(work, "claude")
    results = []
    try:
        rc, out = run(["git", "clone", "-q", MIRROR, repo])
        if rc != 0:
            print("[FAIL] clone 失败：%s" % out[-300:])
            return 1

        # 陌生人拿到手的东西里，绝不该有作者的绝对路径
        leaked = []
        for dirpath, dirnames, filenames in os.walk(repo):
            dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
            for fn in filenames:
                if not fn.lower().endswith((".py", ".md", ".spec", ".json", ".js", ".yml")):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    with open(p, encoding="utf-8", errors="replace") as f:
                        t = f.read()
                except OSError:
                    continue
                # 「C:\Users\<某人>」这种讲道理的示例文字不算，带真实用户名的才算
                if "C:\\Users\\Administrator" in t:
                    leaked.append(os.path.relpath(p, repo))
        results.append(("clone 里没有作者的绝对路径" +
                        ("" if not leaked else "（泄漏：%s）" % ", ".join(leaked[:3])),
                        not leaked))

        rc, out = run([PY, "-X", "utf8", os.path.join(repo, "install.py"),
                       "--claude-dir", fake_claude], cwd=repo)
        bad = [ln for ln in out.splitlines() if "[XX]" in ln]
        results.append(("install.py 退出 0 且零 [XX]（实际 rc=%d, %d 条红）" % (rc, len(bad)),
                        rc == 0 and not bad))

        rc, out = run([PY, "-X", "utf8", os.path.join(repo, "dashboard.py"), "--selftest"], cwd=repo)
        n = out.count("  ok ")
        results.append(("源码态 selftest 全过（%d 项，rc=%d）" % (n, rc), rc == 0 and n >= 20))

        if not FULL:
            print("[i] 跳过打包两步（约 40 秒）——要跑加 --full 或设 CLONE_SMOKE_FULL=1")
        else:
            try:
                import PyInstaller  # noqa
                has_pi = True
            except ImportError:
                has_pi = False
            if not has_pi:
                print("[SKIP] 没装 PyInstaller，跳过打包两步")
            else:
                rc, out = run([PY, "-m", "PyInstaller", "lingtaios.spec", "--noconfirm"], cwd=repo)
                exe = os.path.join(repo, "dist", "lingtaios.exe")
                results.append(("clone 里打得出包（rc=%d）" % rc, rc == 0 and os.path.isfile(exe)))
                if os.path.isfile(exe):
                    rc, out = run([exe, "--selftest"])
                    n = out.count("  ok ")
                    results.append(("打出来的 exe selftest 全过（%d 项，rc=%d）" % (n, rc),
                                    rc == 0 and n >= 20))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    for name, ok in results:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
    bad = [n for n, o in results if not o]
    print("\n%s" % ("ALL PASSED" if not bad else "SOME FAILED"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
