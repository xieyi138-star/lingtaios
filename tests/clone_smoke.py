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
HOME = os.path.expanduser("~")   # 本机真实家目录，运行时取，不写死
PY = sys.executable
DN = subprocess.DEVNULL
FULL = "--full" in sys.argv or os.environ.get("CLONE_SMOKE_FULL") == "1"

# 发布仓在哪，只有一个真源：release_sync.py 的 resolve_mirror()。
# ⛔ 这里曾经自己写一份 `os.environ.get("LINGTAI_MIRROR") or r"D:\tmp\lingtaios-repo"`。
#    两个毛病叠在一起：① 第二份真源；② 兜底指着一个早就挪走的路径。
#    于是环境变量没传进来时它静默跳过、还 return 0 被 runner 判绿——
#    这条本该「照出布局失配」的红线，连着若干窗一次都没真跑过。
SYNC = os.path.join(BC, "release_sync.py")


def _mirror():
    """返回 (路径, 来源)。release_sync.py 不在 = 陌生人从公开仓 clone 出来的副本。"""
    if not os.path.isfile(SYNC):
        return None, None
    if BC not in sys.path:
        sys.path.insert(0, BC)
    import release_sync
    return release_sync.resolve_mirror()


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode, (r.stdout or b"").decode("utf-8", errors="replace")


def main():
    # 退出码约定：0 绿 / 1 红 / 3 跳过（runner 单独计一档，永远不并进绿）
    if not os.path.isfile(SYNC):
        print("[SKIP] 没有 release_sync.py —— 这是主源码专属的发布工具，")
        print("       从公开仓 clone 出来的副本里本来就没有它，没有发布仓可验。")
        return 3
    mirror, msrc = _mirror()
    if not mirror:
        print("[FAIL] 主源码在，却不知道发布仓在哪——这台就是作者机器，")
        print("       所以这不是「无从校验」，是配置坏了。")
        print("       在 %s 里写一行发布仓路径即可。" % os.path.join(BC, ".mirror_path"))
        return 1
    print("[i] 发布仓 %s（来自 %s）" % (mirror, msrc))
    if not os.path.isdir(os.path.join(mirror, ".git")):
        print("[FAIL] %s 不是 git 仓——来源 %s 指错了地方。" % (mirror, msrc))
        return 1
    if shutil.which("git") is None:
        print("[SKIP] 没有 git，clone 不了")
        return 3

    work = tempfile.mkdtemp(prefix="clone_smoke_")
    repo = os.path.join(work, "clone")
    fake_claude = os.path.join(work, "claude")
    results = []
    try:
        rc, out = run(["git", "clone", "-q", mirror, repo])
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
                # 找的是**本机真实家目录**出现在发布物里，不是「C:\Users\<你>」这种示例写法。
                # ⛔ 别把用户名写死在这一行——写死了换台机器就检测不到，而且这行自己
                #    会被自己的检测抓到（第一次就是这么被 GitHub clone 扫出来的）。
                if HOME in t:
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
