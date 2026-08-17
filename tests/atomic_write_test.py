# -*- coding: utf-8 -*-
"""守：写文件失败时，原文件必须原样还在。

为什么要有它
------------
`open(path, "w")` 是**先把原文件截断成 0，再往里写**。中途出任何事——编码错、
磁盘满、断电、进程被杀——原文件就没了，而且**看起来像什么都没发生**。

这不是假想。本窗真发生过：一次改 dashboard.py 时字符串里混进了游离代理对
（`\ud800` 这种落单的半个 emoji），写到一半编码抛异常，127548 字节的文件
当场变成 0 字节，靠 git 才捞回来。

用户的坑库、roots.json、项目的六器官**没有 git 兜着**。「记忆归你」这条承诺，
第一步是别把它写没了。所以所有写用户数据的地方都走 _atomic_write：
先写 .tmp，成功了再 os.replace（同分区上是原子的）。

测试用例就用当初那个错：往里塞一个游离代理对，必然编码失败。
⛔ 全程在临时目录，不碰任何真文件。
"""
import io
import os
import shutil
import sys
import tempfile

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BC)
sys.path.insert(0, os.path.join(BC, "vendor"))
SKILLS = BC if os.path.isdir(os.path.join(BC, "project-delivery")) else os.path.dirname(BC)


def main():
    import dashboard                                     # noqa: E402
    work = tempfile.mkdtemp(prefix="atomic_")
    results = []
    try:
        p = os.path.join(work, "用户的坑库.md")
        good = "| P1 | 一句话坑 | 防法 |\n" * 50
        dashboard._atomic_write(p, good)
        results.append(("正常写：内容对得上", io.open(p, encoding="utf-8").read() == good))
        results.append(("正常写：没留下 .tmp 残骸", not os.path.isfile(p + ".tmp")))

        # ⛔ 造那次真实事故：游离代理对，utf-8 编不出来
        before = io.open(p, "rb").read()
        boom = None
        try:
            dashboard._atomic_write(p, "毁掉你 \ud800 的记忆")
        except (UnicodeEncodeError, UnicodeError) as e:
            boom = type(e).__name__
        results.append(("写失败时确实抛了异常（%s）——不许静默" % boom, boom is not None))
        after = io.open(p, "rb").read()
        results.append(("**原文件逐字节没变**（%d 字节）" % len(after), after == before))
        results.append(("失败后没留下 .tmp 残骸", not os.path.isfile(p + ".tmp")))

        # 对照：老写法在同样的输入下会把文件干成 0 字节
        q = os.path.join(work, "老写法.md")
        io.open(q, "w", encoding="utf-8").write(good)
        try:
            with io.open(q, "w", encoding="utf-8") as f:
                f.write("毁掉你 \ud800 的记忆")
        except (UnicodeEncodeError, UnicodeError):
            pass
        results.append(("对照：老写法（open 'w'）同样输入下把文件写成了 %d 字节"
                        % os.path.getsize(q), os.path.getsize(q) == 0))

        # 生成器里那份也得是原子的——它会被复制进用户的每个项目
        sys.path.insert(0, os.path.join(SKILLS, "project-delivery", "scaffold"))
        import importlib.util
        gp = os.path.join(SKILLS, "project-delivery", "scaffold", "状态生成器.py")
        spec = importlib.util.spec_from_file_location("gen_mod", gp)
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        r = os.path.join(work, "02_状态.md")
        gen.atomic_write(r, good)
        b2 = io.open(r, "rb").read()
        try:
            gen.atomic_write(r, "坏 \ud800 内容")
        except (UnicodeEncodeError, UnicodeError):
            pass
        results.append(("状态生成器也用原子写，失败后原文件没变",
                        io.open(r, "rb").read() == b2))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    for name, ok in results:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
    bad = [n for n, o in results if not o]
    print("\n%s" % ("ALL PASSED" if not bad else "SOME FAILED"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
