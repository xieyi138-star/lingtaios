# 灵台 LingTai OS · 个人 Agent OS

> **一句话**：任何 AI 装进来就有纪律、记忆、状态和自进化——换模型不丢记忆，换电脑一条命令可用。
> **一条命令**：`python -X utf8 install.py && python -X utf8 dashboard.py`

## 五页

| 页 | 内容 | 数据来源（只读，零副本） |
|---|---|---|
| 总览 | 装配图七层导航 + 真源健康检查红绿灯 + 本机根状态 | 装配图.md + roots.json + 实盘 Test-Path |
| 项目 | 各项目六器官卡片 + 状态红绿 | 各项目 `状态生成器.py` 产出的 02_状态.json（机器生成） |
| 坑库 | 跨项目 B 坑表格 + 分区筛选 + 搜索 | 坑库.md |
| 方法 | 薄核/道法术/项目交付法/核心大脑只读浏览 | 四真源 .md |
| 移植 | 装机说明 + 当前 roots + machine_id | roots.json |

## 换电脑三步

1. clone 本仓库（skills）到新机器
2. `python -X utf8 install.py`（自动探测各根；没有 Nexus/D 根就跳过——业务页会显示"本机无此根"）
3. `python -X utf8 dashboard.py`（起本地服务并开浏览器）

## 团队版预留（v0.1 已架构、未实现）

- `roots.json` 带 `machine_id`：多机/多成员的数据模型从第一天就分得开
- 页面结构按多项目卡片设计；网络同步/账号系统留给 v0.2（另立项）

## No-gos

- 零 pip/npm 依赖（vendor/mistune.py 为 MIT 单文件渲染库，随仓）
- 不复制任何真源内容（渲染即读，关掉服务什么都不会留下，除了 site/ 生成物）
- 不碰涉密文件（装配图只登记不渲染内容）
