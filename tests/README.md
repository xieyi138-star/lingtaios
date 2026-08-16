# 回归测试集

2026-08-16 那一轮改造（exe 瘦身 / 项目库 / 首跑向导 / 界面走查）沉淀下来的**可重复跑**的验证脚本。
一次性的探针和补丁脚本没有留，只留能反复跑的。

## 怎么跑

```
python -X utf8 tests\stress_a.py
```

cwd 无所谓，脚本自己定位（`BC` 从 `__file__` 推）。

⛔ **每个脚本跑完都会清掉 8765 上的进程**（它们要独占端口做测试）。
跑完记得把服务起回来，否则浏览器里那个页面会报 `TypeError: Failed to fetch`：

```
Start-Process dist\lingtaios.exe -WorkingDirectory dist
```

⛔ 脚本一律用 `--roots-file` 指向临时沙盒，**不碰真 roots.json 和真 site/data.json**。
`no_pollute_test.py` 就是专门守这条的——它比对操作前后两个真文件的 md5。

## 清单

| 脚本 | 验什么 | 通过基线 |
|---|---|---|
| `stress_a.py` | 启动语义与端口竞争：干净启动、exe vs exe、python vs exe、4 路并发、非灵台程序占位 | 8/8 |
| `stress_b.py` | 路由覆盖、200 并发、全新下载独立跑、`--selftest`/`--health` | 13/13 |
| `destructive_probe.py` | 探针失败必须报红：属性缺失/模块抛错/语法错/`len()` 不适用/模块不存在 | 6/6 |
| `project_mgmt_stress.py` | 项目管理 13 个维度：安全/幂等/来源/边界/并发/持久/输入/撤销/回流/鲁棒/隔离 | 39 项全过 |
| `exe_mgmt_check.py` | 项目管理在打包后的 exe 里同样可用，且**文件一个不动** | 9/9 |
| `dedup_front.js` | 去重逻辑单测（需要 node） | 13/13 |
| `dedup_back_e2e.py` | 后端去重兜底：被工作区罩住的不重复登记 | 10/10 |
| `no_pollute_test.py` | **演练绝不污染真源**（真 roots.json / 真 data.json md5 不变） | 全 PASS |
| `workspace_e2e.py` | 工作区模式：浏览→设区→保存→动态发现→排除 | 12/12 |
| `finder_e2e.py` | 「帮我找找」：埋在深处的工作区能找到、资源目录被排除 | 7/7 |
| `wizard_v3_e2e.py` | 首跑向导：浏览列文件、扫描出清单、动态发现、防污染 | 13/13 |
| `brand_check.py` | 品牌/侧栏/logo/开发者信息**在 exe 里**是否正确 | 15/15 |
| `soul_manifest.py` | **灵魂 20 件**：把 exe 剖开，逐件与 skills 真源比 md5 | 一致 20，缺失 0 |
| `two_form_parity.py` | **两态一致性**：同一份 roots，源码态 vs exe 态 21 项逐项比 | 18 一致，0 个不该有的差异 |
| `native_pick_e2e.py` | 原生文件夹对话框能弹、置顶、拿到真实路径 | 6/6 |
| `pick_lock_test.py` | 对话框开着时重复点被拒（409），不弹第二个 | 4/4 |
| `nav_check.py` | 侧栏文案在 exe 里正确 | 全 PASS |
| `detail_live_check.py` | 对着正在跑的服务，把每个项目详情逐个打开 | 全 200 |

## 全量跑一遍

```
python -X utf8 tests\soul_manifest.py
python -X utf8 tests\two_form_parity.py
python -X utf8 tests\stress_a.py
python -X utf8 tests\stress_b.py
python -X utf8 tests\destructive_probe.py
python -X utf8 tests\project_mgmt_stress.py
python -X utf8 tests\exe_mgmt_check.py
python -X utf8 tests\no_pollute_test.py
python -X utf8 tests\workspace_e2e.py
python -X utf8 tests\finder_e2e.py
python -X utf8 tests\wizard_v3_e2e.py
python -X utf8 tests\dedup_back_e2e.py
python -X utf8 tests\brand_check.py
node tests\dedup_front.js
```

## 注意

- 脚本里**不含任何绝对路径**：`BC` 从 `__file__` 推（tests 的上一级），`EXE` 在
  `release_pkg\` 和 `dist\` 里挑存在的那个。所以从任意 cwd、任意机器 clone 下来都能直接跑。
  （2026-08-16 之前这里写死 `C:\Users\Administrator\...`，换台机器整套跑不起来——同一个病 spec 里也犯过。）
- 改了 `dashboard.py` / `web/` 之后要**先重新打包**再跑那些验 exe 的脚本
  （`soul_manifest` / `two_form_parity` / `exe_mgmt_check` / `brand_check` / `nav_check` / `stress_*`），
  否则验的是旧 exe。
