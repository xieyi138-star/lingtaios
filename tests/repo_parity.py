# -*- coding: utf-8 -*-
"""守「发布镜像仓同名文件必须与主源码逐字节一致」这条红线。

这条红线以前只写在 HANDOFF 里，没有任何东西在执行它，代价付过两次：
内部开发说明覆盖了产品首页；lingtaios.spec / tests / 接入卡长期没进发布仓，
公开仓 clone 下来 install.py 12 项全红、装不上。

本脚本不自己实现比对逻辑——那样又会出现第二份真源。它调用
release_sync.py --check，那里的映射表是唯一权威。
"""
import os
import subprocess
import sys

BC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # tests 的上一级
SYNC = os.path.join(BC, "release_sync.py")


def main():
    # ⛔ 兜底必须出声：跳过的理由要打出来，不能静默 PASS 让人以为守住了。
    if not os.path.isfile(SYNC):
        print("[SKIP] 没有 release_sync.py —— 这是主源码专属的发布工具，")
        print("       从公开仓 clone 出来的副本里本来就没有它，跳过属于预期。")
        return 0

    r = subprocess.run([sys.executable, "-X", "utf8", SYNC, "--check"],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = (r.stdout or b"").decode("utf-8", errors="replace")
    print(out.rstrip())

    if r.returncode == 0:
        print("\n[PASS] 两仓逐字节一致，且主源码无未登记去向的文件")
        return 0
    if "发布仓不存在" in out:
        print("\n[SKIP] 本机没有发布仓（只在作者机器上有），这条红线在此机无从校验")
        return 0
    print("\n[FAIL] 两仓不一致或有未登记文件——跑 release_sync.py --apply 修，")
    print("       新增文件先去 release_sync.py 的映射表里登记去向")
    return 1


if __name__ == "__main__":
    sys.exit(main())
