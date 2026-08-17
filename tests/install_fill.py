# -*- coding: utf-8 -*-
"""装六器官时，代码要填的每一处出厂模板都必须真的被填上。

为什么要有它
------------
装六器官是十来处 `text.replace(模板原句, 实际内容)`。模板哪天改了一个字，
replace **不报错、不抛异常、返回的还是个完整字符串**——它只是什么都没换。
用户装完打开 00_宪法.md，看到的是 `# 宪法 · <项目名>`，而安装那一步显示成功。
「工具返回成功 ≠ 事情做成了」的标准形状，而且模板和代码分属两个文件、
各自都能独立修改，漂移是迟早的事。

两道断言，缺一不可：
  1. 真装一遍（新装 + 续装两种），代码记的账 `_install_misses` 必须是空的；
  2. 装的那段源码里**不许有任何裸 `.replace(` 作用在模板文本上**——都得走 `_fill`。
     只有第 1 条的话，哪天有人新加一处 replace 忘了走 _fill，它漏不掉却也测不到：
     记账里根本没有这一条，永远是空的。

⛔ 不去查「装出来的文件里还有没有 <...>」——模板里本来就留着大量给人后填的占位
   （证据头格式示例、果五栏判定方式…），那是设计，不是漏填。分不清就会天天假红，
   假红久了没人看。
"""
import inspect
import io
import os
import re
import shutil
import sys
import tempfile

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BC)

import dashboard  # noqa: E402

# 装那一段里，承载出厂模板正文的局部变量。它们身上不许出现裸 .replace(
TEMPLATE_VARS = ("const", "codex", "plan", "hand")


def main():
    fails = []

    # ── 1. 真装一遍，两种模式都验
    for retro in (False, True):
        tmp = tempfile.mkdtemp(prefix="install_fill_")
        try:
            brain = dashboard._install_organs_files(
                tmp, u"测试项目", goals=[], redlines=[], retro=retro)
            misses = list(dashboard._install_misses)
            if misses:
                fails.append(u"retro=%s：%d 处模板没填上 → %s" % (retro, len(misses), misses))
            # 顺手确认这次装的确实换过东西（记账为空也可能是**一处都没调用**）
            with io.open(os.path.join(brain, u"00_宪法.md"), encoding="utf-8") as f:
                head = f.read()
            if u"# 宪法 · 测试项目" not in head:
                fails.append(u"retro=%s：00_宪法.md 的标题没换成项目名" % retro)
            print(u"  retro=%-5s 装完：记账漏填 %d 处，标题 %s"
                  % (retro, len(misses),
                     u"已换" if u"# 宪法 · 测试项目" in head else u"**没换**"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ── 2. 源码层：模板文本一律走 _fill，不许裸 replace
    src = inspect.getsource(dashboard._install_organs_files)
    bare = []
    for v in TEMPLATE_VARS:
        for m in re.finditer(r"\b%s\s*=\s*%s\.replace\(|\b%s\.replace\(" % (v, v, v), src):
            bare.append(v)
    if bare:
        fails.append(u"这些模板变量上还有裸 .replace（模板改一个字就静默失效）：%s"
                     % ", ".join(sorted(set(bare))))
    n_fill = len(re.findall(r"_fill\(", src)) - 1  # 减掉 def 那一行
    print(u"  源码：_fill 调用 %d 处，裸 replace %d 处" % (n_fill, len(bare)))
    if n_fill < 8:
        fails.append(u"_fill 只有 %d 处，比预期少——是不是有替换绕过了记账" % n_fill)

    if fails:
        print(u"[FAIL] %d 条" % len(fails))
        for x in fails:
            print(u"  - " + x)
        return 1
    print(u"[OK] 出厂模板每一处都填上了，且没有绕过记账的替换")
    return 0


if __name__ == "__main__":
    sys.exit(main())
