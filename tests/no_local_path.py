# -*- coding: utf-8 -*-
"""要发出去的文件里，不许出现**你自己机器上的用户名/本机专属路径**。

为什么要有它
------------
红线原文：「任何代码/文档里都不许再写死 C:\\Users\\...」。它一直只是一句话，
没有任何东西在守——于是 `project-delivery/hooks/settings.snippet.json` 里写着
作者的真实路径，一路同步进了公开仓，差一步就 push 出去。

拦下它的是 push 前的手工 grep。而那次 grep **第一遍还漏了**：
模式按单反斜杠写，而 JSON 里是转义后的双反斜杠，结果报了「0 条」——
「查了，没有」和「模式错了，什么都查不到」长得一模一样（坑库 T13）。
所以这里的判据必须自带反向断言：先证明扫描器能查到一个**已知存在**的样本。

判据为什么用「当前用户名」
--------------------------
不把某个具体用户名写进判据——那本身就是硬编码，而且换个人就失效
（写了会被这条检查自己抓住，实测过一次）。
取 `os.path.expanduser("~")` 的末段：**你自己的用户名，不该出现在要发给别人的文件里**。
这条在任何人的机器上都成立，也不需要维护名单。

⚠️ 在 CI 上（runner 用户名是 runner/runneradmin）这条几乎恒绿——它主要在作者
机器上有意义。反向断言保证它就算恒绿也不是哑的。

退出码：0 干净 / 1 有违规
"""
import io
import os
import re
import sys

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BC)

TEXT_EXT = {".md", ".py", ".json", ".ps1", ".sh", ".yml", ".yaml", ".txt",
            ".html", ".css", ".js", ".spec"}


def shipped_files():
    """要发布出去的文件清单。取 release_sync 的映射表，不自己再列一份（P10）。"""
    try:
        import release_sync
    except ImportError:
        return None
    return [src for src, _dst, _rel in release_sync.plan()]


def scan(paths, needle):
    """返回 [(文件, 行号, 该行)]。needle 按字面找，大小写不敏感。"""
    hits = []
    low = needle.lower()
    for p in paths:
        if os.path.splitext(p)[1].lower() not in TEXT_EXT:
            continue
        try:
            with io.open(p, encoding="utf-8", errors="replace") as f:
                for i, ln in enumerate(f, 1):
                    if low in ln.lower():
                        hits.append((p, i, ln.strip()[:120]))
        except OSError:
            continue
    return hits


def main():
    me = os.path.basename(os.path.expanduser("~")).strip()
    print("当前用户名：%s" % me)
    if not me or len(me) < 3:
        print("[跳过] 取不到可判别的用户名（太短，会误伤）")
        sys.exit(3)

    files = shipped_files()
    if files is None:
        print("[跳过] 导不了 release_sync，拿不到发布清单")
        sys.exit(3)
    files = [p for p in files if os.path.isfile(p)]
    print("发布清单：%d 个文件" % len(files))

    # ---- 反向断言先跑：证明扫描器真的能查到东西 -------------------------
    # ⛔ 顺序不能反。先跑正向、绿了就收工的话，模式写错造成的「0 条」
    #    和真的干净长得一模一样——上一次就是这么漏的。
    # ⛔ 扩展名必须落在 TEXT_EXT 里，否则 scan 直接跳过它。
    #    第一版用的 .tmp，反向断言当场就红了——它抓到的第一个缺陷是**它自己的**。
    #    这正是这条断言存在的理由：先证明尺子能读出非零值（坑库 P8）。
    probe = os.path.join(BC, "_no_local_path_probe.json")
    try:
        with io.open(probe, "w", encoding="utf-8") as f:
            f.write('{"p": "C:\\\\Users\\\\%s\\\\.claude"}\n' % me)
        found = scan([probe], me)
        if not found:
            print("[XX] 反向断言失败：扫描器连**故意放进去的**样本都查不到。")
            print("     此时报「没有违规」是假绿，直接判红。")
            sys.exit(1)
        print("[OK] 反向断言：扫描器能查到已知样本（%s:%d）" % (os.path.basename(probe), found[0][1]))
    finally:
        try:
            os.remove(probe)
        except OSError:
            pass

    # ---- 正向：发布清单里不许出现 -----------------------------------------
    hits = scan(files, me)
    # JSON 转义（C:\\Users\\name）和裸路径（C:\Users\name）都会命中上面这条，
    # 因为判据只找用户名本身，不依赖反斜杠的写法——那正是上次漏检的根源。
    if hits:
        print("\n[XX] 要发布的文件里出现了本机用户名 %d 处：" % len(hits))
        for p, i, ln in hits[:20]:
            print("  %s:%d" % (os.path.relpath(p, os.path.dirname(BC)), i))
            print("      %s" % ln)
        print("\n改成占位符（如 <SKILLS_ROOT>）或运行时探测。")
        print("红线：任何代码/文档里都不许写死用户路径——对读者没意义，还泄露你的目录布局。")
        sys.exit(1)

    print("[OK] 发布清单里没有本机用户名")
    print("ALL PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
