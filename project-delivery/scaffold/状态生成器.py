# -*- coding: utf-8 -*-
"""状态生成器 · 核心大脑器官② —— 通用，不绑定任何项目。

【为什么必须是机器生成】
人写的完成度表，写完当天就可能过期，**而且不会报错**。
实测：某项目总图记「道 14/17 未完成」，实读代码是 17/17 全完成——
在过期的图上找位置，找到的是错的位置。

【设计原则】
1. 只从**真源**取数（代码常量 / 文件系统 / 产物），不从任何文档取数。
2. **取数失败必须出声**，绝不静默返回 0——安全的兜底和正确的读数长得一样。
3. 每个数都带**取数方式**，事后能复算。
4. 可声明 `expect`：漂了就红（对账闸）。

用法：
    python -X utf8 状态生成器.py                 # 生成 状态.md + 状态.json
    python -X utf8 状态生成器.py --dir <brain>   # v0.7 共享化：从 skills 真源直跑任意项目
    python -X utf8 状态生成器.py --check         # 只校验，有红就退出码 1（可进回归）
    python -X utf8 状态生成器.py --selftest      # 零依赖自检
"""
import glob as _glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(HERE, "状态源.json")
OUT_MD = os.path.join(HERE, "02_状态.md")
OUT_JSON = os.path.join(HERE, "02_状态.json")


class ProbeError(Exception):
    pass


class ToolBroken(ProbeError):
    """**量具自己坏了**，不是产物变了。

    ⛔ 这两种红必须分开，因为处理方式相反：
       产物变了 → 该写下去，让人看见变化；
       量具坏了 → **绝不能写下去**，那会用一堆「取数失败」覆盖掉上一次的真数，
                  而覆盖之后旧数就再也拿不回来了（除非有人恰好备份过）。
       实测：exe 里打包的 Python 没有 sqlite3，`lingtaios.exe --regen` 把
       IPGuard 一份 10 个探针全绿的状态覆盖成了 11 条「取数失败」。
    """


# ── 探针实现 ──────────────────────────────────────────────
# 每个探针返回 (值, 取数方式说明)。取不到一律抛 ProbeError，不返回 0。

def _files(root, pattern):
    return sorted(_glob.glob(os.path.join(root, pattern), recursive=True))


def p_file_count(root, spec):
    fs = _files(root, spec["glob"])
    return len(fs), u"glob `%s` → %d 个文件" % (spec["glob"], len(fs))


def _read(path):
    """读文本。**必须用 utf-8-sig**：PowerShell 写的文件默认带 UTF-8 BOM，
    BOM 会粘在第一行行首，让 `^xxx` 这类行首锚定的正则**在第一行永远不匹配**——
    静默少数一条，永不报错。实测：两个 `def check_` 只数出 1。
    这是「量具比被测对象更容易错」的活样本，故此处写死不许改回 utf-8。"""
    with io.open(path, encoding="utf-8-sig", errors="replace") as fh:
        return fh.read()


def p_regex_count(root, spec):
    fs = _files(root, spec["glob"])
    if not fs:
        raise ProbeError(u"glob `%s` 一个文件都没匹配到" % spec["glob"])
    rx = re.compile(spec["pattern"], re.M)
    n = 0
    for f in fs:
        n += len(rx.findall(_read(f)))
    return n, u"在 %d 个文件里数 `%s` → %d" % (len(fs), spec["pattern"], n)


_HOST_PY = "未找过"


def _host_python():
    """找一台机器上现成的 Python 3（打包态自己那份不带项目要的模块）。没有返回 None。

    「零依赖」的意思是**不许要求**用户装 Python，不是不许用他已经装了的那个。
    装了就借来跑一趟（顺带把子进程隔离也拿回来了），没装才认输。
    """
    global _HOST_PY
    if _HOST_PY != "未找过":
        return _HOST_PY
    cands = []
    for c in ("python", "python3"):
        p = shutil.which(c)
        if p:
            cands.append([p])
    p = shutil.which("py")
    if p:
        cands.append([p, "-3"])
    _HOST_PY = None
    for cmd in cands:
        try:
            # Windows 上 PATH 里那个 python.exe 可能是应用商店的占位程序：带参数跑
            # 会直接非零退出（只有不带参数才会弹商店），所以这一句就能把它筛掉。
            r = subprocess.run(cmd + ["-c", "import sys;print(sys.version_info[0])"],
                               capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and (r.stdout or "").strip() == "3":
                _HOST_PY = cmd
                break
        except (OSError, subprocess.TimeoutExpired, ValueError):
            continue
    return _HOST_PY


def _import_len_via(cmd, d, name, attr):
    """用给定解释器起子进程导入模块取长度。失败抛 ProbeError。"""
    code = (
        "import sys,json\n"
        "sys.path[:0]=[%r]\n"
        "import %s as M\n"
        "print(json.dumps({'n': len(getattr(M, %r))}))\n"
        % (d, name, attr)
    )
    r = subprocess.run(cmd + ["-X", "utf8", "-c", code],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=d, timeout=120)
    if r.returncode != 0:
        raise ProbeError(u"导入失败：%s" % (r.stderr or "")[-200:])
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])["n"]
    except Exception:
        raise ProbeError(u"输出解析失败：%s" % r.stdout[:200])


def p_py_attr_len(root, spec):
    """导入一个模块，取某个属性的长度。用于「道层原理数」这类真源在代码里的量。"""
    path = os.path.join(root, spec["module"])
    if not os.path.exists(path):
        raise ProbeError(u"模块不存在：%s" % path)
    d = os.path.dirname(path)
    name = os.path.splitext(os.path.basename(path))[0]

    if getattr(sys, "frozen", False):
        # ⛔ 打包环境（灵台 exe）里 sys.executable 是宿主 exe，不是 python.exe。
        # 拿它当解释器起隔离子进程 → 「unrecognized arguments: -X utf8 -c ...」，
        # 探针会假报红：数其实好好的，红的是量具自己。
        # → 先退回进程内导入：隔离性没了（在自己的解释器里 exec 用户模块），但取得到真数。
        #   进程内导入缺模块时，再借机器上现成的 Python 跑一趟（见 _host_python）。
        import importlib.util
        sys.path.insert(0, d)
        try:
            spec_obj = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec_obj)
            spec_obj.loader.exec_module(mod)
            n = len(getattr(mod, spec["attr"]))
        except ImportError as e:
            # ⛔ 缺模块 = **量具自己跑不了**，不是产物变了。
            #    exe 里打包的 Python 只带了生成器自己用到的标准库；项目探针
            #    import 什么（sqlite3 / numpy / pandas…）打包时根本不知道。
            #    实测：IPGuard 的 probe 要 sqlite3，exe 里没有，11 个探针全红。
            #    先借机器上现成的 Python 救一把；救不了才认输——而这种红
            #    **绝不能当成新状态写下去**，见 main() 里的拦截。
            host = _host_python()
            if host:
                try:
                    n = _import_len_via(host, d, name, spec["attr"])
                except ProbeError as e2:
                    # 借来的 Python 也跑不动：可能是它也缺这个包，也可能是项目模块真坏了。
                    # 分不清就往「量具坏了」判——判错的代价不对等：
                    # 判成量具坏 = 状态不更新（可补救）；判成产物变了 = 好数据被覆盖（不可逆）。
                    raise ToolBroken(u"exe 内缺模块，借本机 Python 重试仍失败：%s" % e2)
                return n, u"`%s`.%s → len=%d（借本机 Python 子进程导入·exe 内缺模块）" % (
                    spec["module"], spec["attr"], n)
            raise ToolBroken(u"进程内导入失败（打包环境缺模块），本机也没找到 Python：%s"
                             % repr(e)[:160])
        except Exception as e:
            raise ProbeError(u"进程内导入失败：%s" % repr(e)[:200])
        finally:
            if sys.path and sys.path[0] == d:
                sys.path.pop(0)
            sys.modules.pop(name, None)
        return n, u"`%s`.%s → len=%d（进程内导入·打包环境无子进程隔离）" % (
            spec["module"], spec["attr"], n)

    n = _import_len_via([sys.executable], d, name, spec["attr"])
    return n, u"`%s`.%s → len=%d（子进程导入，隔离环境）" % (spec["module"], spec["attr"], n)


def p_json_path(root, spec):
    path = os.path.join(root, spec["file"])
    if not os.path.exists(path):
        raise ProbeError(u"文件不存在：%s" % path)
    with io.open(path, encoding="utf-8") as f:
        d = json.load(f)
    cur = d
    for k in spec["path"].split("."):
        if isinstance(cur, list):
            cur = cur[int(k)]
        else:
            cur = cur[k]
    return cur, u"`%s` 的 %s → %s" % (spec["file"], spec["path"], cur)


def p_declared(root, spec):
    """人工声明的值。**故意做成一等公民并显式标记**——
    因为伪装成自动值的手写数，正是「过期的图」的来源。"""
    return spec["value"], u"⚠ 人工声明（非自动取数）：%s" % spec.get("why", "")


PROBES = {
    "file_count": p_file_count,
    "regex_count": p_regex_count,
    "py_attr_len": p_py_attr_len,
    "json_path": p_json_path,
    "declared": p_declared,
}


# ── 主流程 ────────────────────────────────────────────────

def atomic_write(path, text):
    """先写同目录临时文件，成功了再原子替换。

    ⛔ `open(path, "w")` 是**先把原文件截断成 0，再往里写**。中途出任何事
       （编码错、磁盘满、断电、进程被杀）原文件就没了，而且看起来像什么都没发生。
       02_状态 虽然能重算，但同一个毛病不该在这套东西里留两套写法——
       这个文件会被复制进用户的每一个项目，写坏一次就是坏一次。
       os.replace 在同分区上是原子的：要么旧的，要么新的，没有中间态。
    """
    tmp = path + ".tmp"
    try:
        with io.open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        # 失败了把半截的 .tmp 收拾掉再往外抛，别在用户项目里堆垃圾
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def run(conf, root, high_water=None):
    """high_water：上一次跑出来的历史最高值（从 02_状态.json 读），给 ratchet 探针用。"""
    high_water = high_water or {}
    rows, alarms = [], []
    vals = {}
    broken = []          # 量具自己跑不了的（缺模块），跟「产物变了」分开收
    for spec in conf.get("probes", []):
        name = spec["name"]
        fn = PROBES.get(spec.get("type"))
        if fn is None:
            alarms.append(u"探针 `%s` 的 type=`%s` 不认识" % (name, spec.get("type")))
            rows.append((name, u"取不到", u"未知探针类型", u"🔴"))
            continue
        try:
            v, how = fn(root, spec)
            vals[name] = v
            flag = u"🟢"
            if "expect" in spec and v != spec["expect"]:
                flag = u"🔴"
                alarms.append(u"**%s 漂了**：期望 %s，实读 %s —— 要么产物变了，要么期望该更新，**必须有人裁决**"
                              % (name, spec["expect"], v))
            # ⛔ 等值 expect 用在**只增不减**的量上，是个必然烂掉的设计：每加一条就红
            #    一次，于是人要么机械改数字、要么学会无视它。实测代价：坑库探针
            #    expect=38，真值一路涨到 80 都没人改，漂了 42 条；而那条告警的原文
            #    写的是「比值下跌 = 坑在流失」——它想守的本来就是**不许减少**。
            #    ratchet 把这件事自动化：涨了自己抬底线（不需要人动手，所以不会烂），
            #    掉了才红（那是删除，本来就该有人裁决）。底线存在生成物 02_状态.json 里，
            #    不写回人手写的 状态源.json——配置归人，读数归机器。
            if spec.get("ratchet"):
                prev = high_water.get(name)
                if prev is not None and v < prev:
                    flag = u"🔴"
                    alarms.append(
                        u"**%s 变少了**：历史最高 %s，实读 %s —— 只增不减的量掉了，"
                        u"要么是走审计删的（那就说清删了哪几条），要么是被改没打招呼，**必须有人裁决**"
                        % (name, prev, v))
            if spec.get("type") == "declared":
                flag = u"🟡"
            rows.append((name, v, how, flag))
        except ToolBroken as e:
            broken.append(u"%s：%s" % (name, e))
            alarms.append(u"**%s 取数失败**：%s" % (name, e))
            rows.append((name, u"取不到", u"❌ %s" % e, u"🔴"))
        except ProbeError as e:
            alarms.append(u"**%s 取数失败**：%s" % (name, e))
            rows.append((name, u"取不到", u"❌ %s" % e, u"🔴"))
    return rows, alarms, vals, broken


def health(conf, vals):
    out = []
    for h in conf.get("health", []):
        a, b = vals.get(h["numerator"]), vals.get(h["denominator"])
        if a is None or b in (None, 0):
            out.append((h["name"], u"算不出", h.get("alarm", "")))
            continue
        out.append((h["name"], round(float(a) / float(b), 2), h.get("alarm", "")))
    return out


def render(conf, rows, alarms, hrows):
    L = []
    w = L.append
    w(u"# 状态 · %s\n" % conf.get("project", "?"))
    w(u"\n> ⛔ **本文件由 `状态生成器.py` 生成，人一个数字都不许手写。**")
    w(u"\n> 手写的状态写完当天就可能过期，而且不会报错。")
    w(u"\n> 生成于 %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))

    if alarms:
        w(u"\n## 🔴 告警（%d 条）—— 先看这里\n\n" % len(alarms))
        for a in alarms:
            w(u"- %s\n" % a)
    else:
        w(u"\n## ✅ 无告警\n")

    w(u"\n## 现状（全部实读，非文档自述）\n\n| | 值 | 怎么取的 | |\n|---|---|---|---|\n")
    for n, v, how, f in rows:
        w(u"| %s | **%s** | %s | %s |\n" % (n, v, how, f))

    if hrows:
        w(u"\n## 健康指标\n\n| 指标 | 值 | 警报条件 |\n|---|---|---|\n")
        for n, v, al in hrows:
            w(u"| %s | **%s** | %s |\n" % (n, v, al))

    oc = conf.get("outcomes", [])
    if oc:
        w(u"\n## 终极之果（**过程量不许进这张表**）\n\n| 指标 | 今天测得到吗 | 说明 |\n|---|---|---|\n")
        ok = 0
        for o in oc:
            m = o.get("measurable")
            ok += 1 if m else 0
            w(u"| %s | %s | %s |\n" % (o["name"], u"✅ 能" if m else u"🔴 不能", o.get("note", "")))
        w(u"\n**能测的：%d / %d**" % (ok, len(oc)))
        if ok == 0:
            w(u"　⛔ **一条都测不到 = 这个果目前是空的，一切读数都没有外部参照。**")
        w(u"\n")

    w(u"\n---\n\n*复算：`python -X utf8 状态生成器.py`。任何文档与本表不一致，**一律信本表并把文档改对**。*\n")
    return u"".join(L)


def _selftest():
    import tempfile, shutil
    d = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(d, "docs"))
        for n in ("a", "b"):
            io.open(os.path.join(d, "docs", "law-%s.md" % n), "w", encoding="utf-8").write(u"x")
        io.open(os.path.join(d, "g.py"), "w", encoding="utf-8").write(u"def check_a():pass\ndef check_b():pass\n")
        # 【论据即测试】BOM 那条教训必须有对应断言，否则注释里那句话是没被检验的散文。
        # PowerShell 写的文件默认带 UTF-8 BOM，BOM 粘在第一行会让 `^` 锚定失配。
        io.open(os.path.join(d, "g_bom.py"), "w", encoding="utf-8-sig").write(u"def check_c():pass\ndef check_d():pass\n")
        conf = {"project": "T", "probes": [
            {"name": "法", "type": "file_count", "glob": "docs/law-*.md"},
            {"name": "闸", "type": "regex_count", "glob": "g.py", "pattern": "^def check_"},
            {"name": "闸BOM", "type": "regex_count", "glob": "g_bom.py", "pattern": "^def check_"},
            {"name": "坏", "type": "regex_count", "glob": "nope/*.py", "pattern": "x"},
            {"name": "期望漂移", "type": "file_count", "glob": "docs/law-*.md", "expect": 99},
            # ratchet：涨了不许吭声、掉了必须红。两个方向都得验——
            # 只验「掉了会红」的话，一个永远报红的实现也能全绿。
            {"name": "棘轮涨", "type": "file_count", "glob": "docs/law-*.md", "ratchet": True},
            {"name": "棘轮掉", "type": "file_count", "glob": "docs/law-*.md", "ratchet": True},
        ], "health": [{"name": "闸/法", "numerator": "闸", "denominator": "法", "alarm": "上升即警报"}]}
        # 历史最高：「棘轮涨」记 1（实读 2，涨了）；「棘轮掉」记 5（实读 2，掉了）
        rows, alarms, vals, _broken = run(conf, d, {"棘轮涨": 1, "棘轮掉": 5})
        ok = True

        def ck(c, m):
            nonlocal ok
            print((u"  ok " if c else u"  ✗ ") + m)
            ok = ok and c
        ck(vals.get("法") == 2, u"file_count 数对")
        ck(vals.get("闸") == 2, u"regex_count 数对")
        ck(vals.get("闸BOM") == 2, u"**BOM 文件也要数对**（实测曾少数 1 条，静默无告警）")
        ck(any(u"取数失败" in a for a in alarms), u"**破坏性**：glob 匹配不到时出声，不静默返回 0")
        ck(any(u"漂了" in a for a in alarms), u"**破坏性**：expect 不符时报红")
        ck(any(u"棘轮掉 变少了" in a for a in alarms), u"**破坏性**：ratchet 掉到历史最高以下报红")
        ck(not any(u"棘轮涨" in a for a in alarms), u"ratchet 涨上去**不报红**（只增不减的量不该每加一条红一次）")
        ck(health(conf, vals)[0][1] == 1.0, u"健康比算对")
        ck(u"人一个数字都不许手写" in render(conf, rows, alarms, health(conf, vals)), u"渲染带红线声明")
        return ok
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    if "--selftest" in sys.argv:
        print(u"状态生成器 · 破坏性自检（零依赖）")
        sys.exit(0 if _selftest() else 1)
    # --dir <brain目录>：从 skills 真源直跑任意项目（v0.7 共享化，项目副本只是快照）
    here = HERE
    if "--dir" in sys.argv:
        i = sys.argv.index("--dir")
        if i + 1 >= len(sys.argv):
            print(u"❌ --dir 缺路径")
            sys.exit(2)
        here = os.path.abspath(sys.argv[i + 1])
    conf_path = os.path.join(here, "状态源.json")
    out_md = os.path.join(here, "02_状态.md")
    out_json = os.path.join(here, "02_状态.json")
    if not os.path.exists(conf_path):
        print(u"❌ 缺配置：%s —— 复制 状态源.示例.json 改名后填自己项目的真源" % conf_path)
        sys.exit(2)
    with io.open(conf_path, encoding="utf-8") as f:
        conf = json.load(f)
    root = os.path.abspath(os.path.join(here, conf.get("root", "..")))
    # 历史最高值存在生成物里（不写回人手写的配置）：配置归人，读数归机器。
    prev_hw = {}
    if os.path.isfile(out_json):
        try:
            with io.open(out_json, encoding="utf-8") as f:
                prev_hw = json.load(f).get("high_water") or {}
        except (ValueError, OSError):
            prev_hw = {}
    rows, alarms, vals, broken = run(conf, root, prev_hw)
    # ⛔ 量具自己跑不了时，**绝不许把这份「全是取数失败」写下去**。
    #    写下去等于用一堆红把上一次的真数永久覆盖掉——旧数再也拿不回来。
    #    实测：exe 里打包的 Python 没有 sqlite3，`lingtaios.exe --regen` 把
    #    IPGuard 一份 10 个探针全绿的状态盖成了 11 条「取数失败」。
    #    「取数失败必须出声」是对的，但出声 ≠ 把失败当成新状态存档。
    if broken:
        print(u"⛔ 没有重算：量具自己跑不了，不是产物变了——保留上一次的状态不动。")
        for x in broken[:6]:
            print(u"   " + x)
        print(u"   多半是这个环境缺项目探针要的模块（打包的 exe 只带生成器自己用到的标准库）。")
        print(u"   用装了这些模块的 Python 跑：python -X utf8 状态生成器.py --dir <brain目录>")
        sys.exit(3)          # 3 = 量具坏了，跟「有告警」的 1 分开
    hrows = health(conf, vals)
    md = render(conf, rows, alarms, hrows)
    if "--check" not in sys.argv:
        # 只对声明了 ratchet 的探针记高水位，且只往上抬——掉下去那次已经报过红了，
        # 把底线跟着降下去等于把告警一次性抹掉，下次再掉就没人知道。
        hw = dict(prev_hw)
        for spec in conf.get("probes", []):
            if not spec.get("ratchet"):
                continue
            v = vals.get(spec["name"])
            if isinstance(v, int):
                hw[spec["name"]] = max(v, prev_hw.get(spec["name"], v))
        atomic_write(out_md, md)
        atomic_write(out_json, json.dumps(
            {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "values": vals,
             "alarms": alarms, "high_water": hw}, ensure_ascii=False, indent=2))
        print(u"written: %s" % out_md)
    for a in alarms:
        print(u"ALARM: " + a)
    sys.exit(1 if alarms else 0)


if __name__ == "__main__":
    main()
