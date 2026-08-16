# 回归测试集

2026-08-16 那一轮改造（exe 瘦身 / 项目库 / 首跑向导 / 界面走查）沉淀下来的**可重复跑**的验证脚本。
一次性的探针和补丁脚本没有留，只留能反复跑的。

## 怎么跑

```
python -X utf8 tests\run_all.py          # 全量，一条命令，跑完自动把服务起回来
python -X utf8 tests\stress_a.py         # 单跑某一个
```

cwd 无所谓，脚本自己定位（`BC` 从 `__file__` 推）。

⛔ **每个脚本跑完都会清掉 8765 上的进程**（它们要独占端口做测试）。
单跑时记得把服务起回来，否则浏览器里那个页面会报 `TypeError: Failed to fetch`
（上一窗就是忘了这步，误报过一次「产品挂了」）：

```
Start-Process dist\lingtaios.exe -WorkingDirectory dist
```

`run_all.py` 把这步做进了 `finally`，跑全量不用记。

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
| `nav_check.py` | 侧栏文案在 exe 里正确 + 进化审计的「判据强度」是只读小节（不能混进勾选删除的清单，否则等于叫人删掉判据弱的坑，正好判反） | 全 PASS |
| `detail_live_check.py` | 对着正在跑的服务，把每个项目详情逐个打开 | 全 200 |
| `repo_parity.py` | **两仓红线**：发布镜像仓同名文件与主源码逐字节一致，且主源码无未登记去向的文件 | 全 PASS |
| `clone_smoke.py` | **坑库 P23 的执行者**：真 clone 发布仓 HEAD，装→跑→打包→自检四步全走，并扫有没有作者的真实用户名 | 全 PASS |
| `persist_after_restart.py` | **坑库 R4 的执行者**：写入→**重启进程**→复查仍在。只验返回码的测试抓不到打包态把临时目录当数据目录 | 全 PASS |
| `fresh_user_e2e.py` | **全新用户第一次打开**：一台没有 NEXUS/D 根、零项目的机器上，服务起得来／首页不白屏／空状态有引导／建得出第一个项目／建完能在列表里看见 | 13 项全 PASS |
| `cn_path_e2e.py` | **解压到中文+空格路径**（「下载\灵台 OS」这种，中国用户的默认情况）：自检／落盘／起服务／中文项目名／建完可见 | 8 项全 PASS |
| `run_all.py` | 全量跑完并自动起回服务（不是被验对象，是跑手） | — |

## 全量跑一遍

```
python -X utf8 tests\run_all.py
```

默认跳过 `native_pick_e2e` / `pick_lock_test`——它们会弹原生文件夹对话框挡在屏幕上；
要跑加 `--with-dialogs`，人别走开。跑完 runner 自己会把 8765 上的服务起回来。

以前这里是 14 条要人一条条敲的命令。漏跑不会有人知道——没跑过的脚本和跑绿的脚本，
在人脑里长得一模一样。

## 注意

- 脚本里**不含任何绝对路径**：`BC` 从 `__file__` 推（tests 的上一级），`EXE` 在
  `release_pkg\` 和 `dist\` 里挑存在的那个。所以从任意 cwd、任意机器 clone 下来都能直接跑。
  （2026-08-16 之前这里写死了作者本机的 `C:\Users\<用户名>\.claude\skills\brain-console`，
  换台机器整套跑不起来——同一个病 spec 和 install.py 里也犯过。连举例都别写真实用户名：
  `clone_smoke.py` 会扫发布仓里有没有真实用户名，写了就报红。）
- 改了 `dashboard.py` / `web/` 之后要**先重新打包**再跑那些验 exe 的脚本
  （`soul_manifest` / `two_form_parity` / `exe_mgmt_check` / `brand_check` / `nav_check` / `stress_*`），
  否则验的是旧 exe。
