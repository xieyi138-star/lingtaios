# 灵台 LingTai OS —— 个人 Agent OS

> **零依赖 · 模型无关 · 记忆归你**
> 你的 AI 不是工具，是精心养护的微型世界。
> 官网：[lingtaios.com](https://lingtaios.com)

## 隐私承诺（第一版就写死，不靠以后补）

- **零遥测**：本软件不含任何上报代码，你的使用数据没有出口
- **记忆全本地**：所有记忆/状态/轨迹存在你自己电脑的文件里，可 diff、可备份、可导出
- **记忆是你的资产**：换模型、换工具、甚至软件死了，记忆文件都还在你手里

一个跑在你本地电脑上的 **个人 Agent OS**：任何 AI（Claude / DeepSeek / 任何支持读文件的模型）装进来，就获得纪律、记忆、状态和自进化——换模型不丢记忆，换电脑一条命令带走。

## 它解决什么

| 痛点 | 本系统 |
|---|---|
| 每个新窗口 AI 都"失忆"，从零考古 | 装配图+交接+轨迹，任何 AI 三句话接上进度 |
| 教训只活在聊天记录里，换个会话就丢 | 坑库（每条带防法+失效判据），踩一次记一条，永久复用 |
| 人写的进度表当天就过期 | 状态机器生成，破坏性自检，绿了才信 |
| 越用越膨胀、垃圾清不掉 | 进化审计：到期/失效/过期自动浮出，一键删除 |
| 体系升级了项目跟不上 | 升级传播：通用件 md5 探针+一键同步，专属件永不覆盖 |

## 5 分钟上手

见 [TUTORIAL.md](TUTORIAL.md)。最短路径：

1. 双击 `lingtaios.exe`（或 `python -X utf8 dashboard.py`）→ 浏览器自动打开驾驶舱
2. 「＋ 新项目」填表 → 六器官自动装好、状态自动生成
3. 点项目卡 → 复制「继续做」指令 → 粘给任何 AI → 开工

## 架构（七层）

```
L1 常驻层  薄核 —— 每条消息都在跑的规则，唯一
L2 方法层  项目交付法/核心大脑/道法术/坑库 —— git 跟踪
L3 经验库  跨项目坑库 + 项目专属坑 —— 各自真源
L4 项目模板 scaffold —— 开新项目整体复制
L5 业务脑  装配图 —— 唯一导航真源
L6 项目层  每项目六器官 —— 状态机器生成
L7 归档层  只读不翻 —— 全登记在装配图
```

## English

**Personal Agent OS** — zero-dependency, model-agnostic, your memory stays yours.

A local-first operating layer for AI collaboration: any AI that can read files inherits discipline (evidence-first rules), memory (pitfall library with invalidation criteria), machine-generated state (self-testing probes), and a growth loop (audit → prune → sync). Switching models never loses your memory; switching machines is one command.

[5-minute tutorial](TUTORIAL.md) · [Demo script](DEMO.md) · Apache-2.0
