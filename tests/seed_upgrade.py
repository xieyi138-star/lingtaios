# -*- coding: utf-8 -*-
"""守出厂文件的升级传播：该升的升，改过的一个字都不许动。

为什么要有它
------------
`_seed_repo` 以前是「不存在才复制」，于是新版带的方法论更新永远不生效
（HANDOFF item 6 挂了好几窗）。根因不是懒，是**分不清哪份是用户改的、
哪份是我们上次写下去的**——分不清就只能一律不动。

现在有了 `.seeded.json` 台账，能分清了，于是三条分支各有各的行为。
这三条里任何一条写反，代价都是**静默**的：
  · 该升的没升 → 用户永远拿不到修好的方法论，而且没有任何提示
  · 改过的被覆盖 → 用户的东西没了，也没有任何提示
所以三条都得有断言，而且都要用「文件内容真的变了 / 真的没变」来判，
不能只看接口说了什么。

⛔ 全程在临时目录里跑一份 exe 的副本，不碰本机任何真源。
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
_CAND = [os.path.join(BC, d, "lingtaios.exe") for d in ("dist", "release_pkg")]
EXE = next((p for p in _CAND if os.path.isfile(p)), None)
DN = subprocess.DEVNULL


def md5(p):
    with io.open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def read(p):
    with io.open(p, "rb") as f:
        return f.read()


def write(p, b):
    with io.open(p, "wb") as f:
        f.write(b)


def main():
    if EXE is None:
        print("[SKIP] 没有打好的 exe——这条只验打包态的播种/升级")
        return 3

    work = tempfile.mkdtemp(prefix="seed_up_")
    app = os.path.join(work, "app")
    os.makedirs(app)
    exe = os.path.join(app, "lingtaios.exe")
    shutil.copyfile(EXE, exe)
    manifest = os.path.join(app, ".seeded.json")
    results = []

    def bump():
        """跑一次 exe：只为触发播种/升级。--regen 指个不存在的目录，播完就退。"""
        subprocess.run([exe, "--regen", os.path.join(work, "nope")],
                       stdout=DN, stderr=DN, timeout=180)

    def state():
        with io.open(manifest, encoding="utf-8") as f:
            return json.load(f)

    try:
        # ── 首跑：落盘 + 建台账 ──────────────────────────────────────────
        bump()
        results.append(("首跑写出了升级台账 .seeded.json", os.path.isfile(manifest)))
        if not os.path.isfile(manifest):
            raise SystemExit(1)
        st = state()
        keys = [k for k in (st.get("files") or {})
                if k.startswith("project-delivery/") and k.endswith(".md")]
        results.append(("台账里记下了出厂文件（%d 个）" % len(keys), len(keys) >= 5))
        key = sorted(keys)[0]
        target = os.path.join(app, key.replace("/", os.sep))
        factory = read(target)          # 出厂内容（刚从包里落下来的）
        results.append(("台账记的哈希 = 落盘那份的哈希",
                        (st["files"].get(key) or "") == md5(target)))

        # ── A 用户改过的，绝不覆盖 ───────────────────────────────────────
        write(target, factory + b"\n\n<!-- USER EDIT DO NOT TOUCH -->\n")
        edited = read(target)
        bump()
        results.append(("A 用户改过的文件没被覆盖（内容逐字节不变）", read(target) == edited))
        results.append(("A 而且它被记进 kept，界面上说得出来", key in (state().get("kept") or [])))

        # ── B 我们上次写的、用户没动过的 → 安全升级 ──────────────────────
        # 造一个「上一版出厂内容」：内容不同，且台账里记的就是它
        old = factory + b"\n\n<!-- SHIPPED BY AN OLDER VERSION -->\n"
        write(target, old)
        st = state()
        st["files"][key] = md5(target)          # 台账说：这就是我们上次写给你的
        with io.open(manifest, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
        bump()
        results.append(("B 没动过的旧版被自动升级成新版（内容回到出厂）",
                        read(target) == factory))
        results.append(("B 升级后台账跟着更新（下次不会重复升）",
                        (state()["files"].get(key) or "") == md5(target)))

        # ── C 台账里没有的（老装机） → 不动，挂到待定 ───────────────────
        write(target, old)
        st = state()
        st["files"].pop(key, None)              # 假装这是 v0.2.0 时代装的
        st["pending"] = []
        with io.open(manifest, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
        bump()
        results.append(("C 认不出来历的文件没被动（内容逐字节不变）", read(target) == old))
        results.append(("C 而且挂进 pending，等人裁决", key in (state().get("pending") or [])))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    for name, ok in results:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
    bad = [n for n, o in results if not o]
    print("\n%s" % ("ALL PASSED" if not bad else "SOME FAILED"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
