# -*- mode: python ; coding: utf-8 -*-

import os as _os

# 路径不许硬编码。写死 'C:\\Users\\<某人>\\.claude\\skills' 的 spec 只在这台机器上成立：
# 别人 clone 公开仓照着打包必然 FileNotFoundError，而且把本机用户名带进了公开仓。
# SPECPATH 是 PyInstaller 注入的「spec 文件所在目录」，一切从它推。
# 两种布局都要认，因为同一份 spec 要在两个仓里逐字节一致：
#   主源码  skills\brain-console\lingtaios.spec  → project-delivery 在**上一级**（兄弟目录）
#   发布仓  repo\lingtaios.spec                  → project-delivery 在**同级**（发布时摊平了）
BC = SPECPATH
SKILLS = BC if _os.path.isdir(_os.path.join(BC, 'project-delivery')) else _os.path.dirname(BC)
GEN = _os.path.join(SKILLS, 'project-delivery', 'scaffold', '\u72b6\u6001\u751f\u6210\u5668.py')
if not _os.path.isfile(GEN):
    raise SystemExit('[spec] 找不到状态生成器，布局判定错了：BC=%s SKILLS=%s' % (BC, SKILLS))
print('[spec] BC=%s' % BC)
print('[spec] SKILLS=%s' % SKILLS)

# 状态生成器.py 是以「数据文件」身份进包的，PyInstaller 的静态分析扫不到它的 import，
# 于是它依赖的 stdlib 不会被打包——exe 里一跑就 ModuleNotFoundError。
# glob 就是这么漏掉的，而且只有真的点「新项目/深查」才暴露，自检以外没人会撞上。
# 所以这里解析生成器的 import 自动补进 hiddenimports：以后生成器加依赖，不用记得回来改 spec。
import ast as _ast
import io as _io


def _imports_of(py):
    try:
        tree = _ast.parse(_io.open(py, encoding='utf-8').read())
    except (OSError, SyntaxError):
        return []
    mods = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for al in node.names:
                mods.add(al.name.split('.')[0])
        elif isinstance(node, _ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module.split('.')[0])
    return sorted(mods)


HIDDEN = sorted(set(['mdlite']) | set(_imports_of(GEN)))
print('[spec] generator deps folded into hiddenimports -> %s' % HIDDEN)

# 版本号进包：界面右上角那个徽章从此读它，不再在 index.html 里存第二份。
# 「一份知识只能存一处，第二处必须由第一处生成」——此前版本号手写在三处，
# 靠 make_release 的一致性检查兜着，而检查只能拦住不一致，拦不住「三处一起忘」。
# 两种布局都要认（主源码在 release\ 下，发布仓摊平后在根）。
VER = _os.path.join(BC, 'release', 'VERSION')
if not _os.path.isfile(VER):
    VER = _os.path.join(BC, 'VERSION')
if not _os.path.isfile(VER):
    raise SystemExit('[spec] 找不到 VERSION：%s' % VER)
print('[spec] VERSION -> %s' % VER)

# 历次版本发出去的出厂文件指纹。升级时靠它判断「这份文件用户改过没有」——
# 等于当年发出去的原样 = 没动过 = 可以安全升级。没有它，旧版装的那批文件
# 就只能挂到界面上问用户「要不要换新版」，而那是个他答不了的问题。
SH = _os.path.join(BC, 'release', 'shipped_hashes.json')
if not _os.path.isfile(SH):
    SH = _os.path.join(BC, 'shipped_hashes.json')
if not _os.path.isfile(SH):
    raise SystemExit('[spec] 找不到 shipped_hashes.json：%s' % SH)

# 不许再把 BC 整个目录打进来。它含 dist/（上一代 exe）和 build/（中间产物），
# 每打一次就把上一代 exe 套进去一次：568MB 里有 508MB 是这么来的，
# 而 dashboard.py 对 'brain-console' 这个 bundle 子目录零引用。
# 需要的东西在下面逐项列全：web/ 是界面，project-delivery/ 是 REPO 真源
# （装配图·坑库·常驻薄核·scaffold/状态生成器），两个 md/json 是 frozen 首跑落盘用的。
a = Analysis(
    [_os.path.join(BC, 'dashboard.py')],
    pathex=[_os.path.join(BC, 'vendor')],
    binaries=[],
    datas=[
        (_os.path.join(BC, 'web'), 'web'),
        (_os.path.join(SKILLS, 'project-delivery'), 'project-delivery'),
        (_os.path.join(SKILLS, 'agent-worksheet'), 'agent-worksheet'),
        (_os.path.join(BC, 'AI\u5f00\u7a97\u5fc5\u8bfb.md'), '.'),
        (_os.path.join(BC, 'roots.example.json'), '.'),
        (VER, '.'),
        (SH, '.'),
    ],
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='lingtaios',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
