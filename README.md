# 灵台 LingTai OS —— 个人 Agent OS

> **零依赖 · 模型无关 · 记忆归你**
> 你的 AI 不是工具，是精心养护的微型世界。
> 官网：[lingtaios.com](https://lingtaios.com) · v0.1.2

## 隐私承诺（第一版就写死，不靠以后补）

- **零遥测**：本软件不含任何上报代码，你的使用数据没有出口
- **记忆全本地**：所有记忆/状态/轨迹存在你自己电脑的文件里，可 diff、可备份、可导出
- **记忆是你的资产**：换模型、换工具、甚至软件死了，记忆文件都还在你手里

## 它解决什么

| 痛点 | 灵台 |
|---|---|
| 每个新窗口 AI 都"失忆"，从零考古 | 装配图+交接+轨迹，任何 AI 三句话接上进度 |
| 教训只活在聊天记录里，换个会话就丢 | 坑库（每条带防法+失效判据），踩一次记一条，永久复用 |
| 人写的进度表当天就过期 | 状态机器生成，破坏性自检，绿了才信 |
| 越用越膨胀、垃圾清不掉 | 进化审计：到期/失效/过期自动浮出，一键删除 |
| 体系升级了项目跟不上 | 升级传播：通用件 md5 探针+一键同步，专属件永不覆盖 |

## 界面

- **墨色/宣纸双主题**：默认墨色，朱砂红+石青矿物色；左下角一键切宣纸
- **首页即仪表**：状态环（真源健康）+ 机器生成时戳 + 「深查」重算全部真源
- **项目卡片**：六器官点阵（绿=新、黄=超 7 天未更新、灰=缺）+ 点击进详情（进度摘要/继续做指令/打开目录/一键装系统）
- **导航只有 2 项**：首页 / 项目——机器自己维护的，不占你的导航

## 怎么拿到

**方式一：下载现成的（推荐，不用装 Python）**

到 [Releases](https://github.com/xieyi138-star/lingtaios/releases) 下载
`lingtaios-vX.Y.Z-win64.zip`，解压到任意目录（**别放 `C:\Program Files` 或桌面临时目录**，
它会在自己旁边写配置和记忆）。目前只有 Windows 64 位版。

> ⚠️ **exe 没有代码签名**，Windows 会弹 SmartScreen「已保护你的电脑」。
> 这是未签名程序的通用提示，不是检出了病毒。要继续：点「更多信息」→「仍要运行」。
> 不放心就走方式二，从源码自己打包——代码全在这儿，你可以先读再跑。

**方式二：从源码自己打包**（需要 Python ≥ 3.8）

```
git clone https://github.com/xieyi138-star/lingtaios.git
cd lingtaios
python -X utf8 install.py          # 探测各根、写 roots.json、补启动器指针
python -X utf8 dashboard.py        # 直接跑源码态，浏览器自动打开
pip install pyinstaller            # 想打成 exe 再装这个
python -m PyInstaller lingtaios.spec
```

`lingtaios.spec` 的路径是自推导的，clone 到哪都能打。打出来在 `dist\lingtaios.exe`。

## 5 分钟上手

1. 双击 `lingtaios.exe`（或 `python -X utf8 dashboard.py`）→ 浏览器自动打开
2. 「＋ 新项目」填表 → 六器官自动装好、状态自动生成
3. 点项目卡 → 复制「继续做」指令 → 粘给任何 AI → 开工
4. 想看进度：双击 → 项目卡；踩坑了：首页「查坑/记坑」

详见 [TUTORIAL.md](TUTORIAL.md) · 演示剧本见 [DEMO.md](DEMO.md)

有问题发 [Issue](https://github.com/xieyi138-star/lingtaios/issues)，或邮件 support@nexusaistart.com / 微信 nexusaistart。

## 换电脑

1. 拷走整个目录（或 clone 本仓库）
2. 跑 `python -X utf8 install.py`（自动探测各根）
3. 跑 `python -X utf8 dashboard.py`

业务数据（本机专属）留原机；方法体系全带走。

## 开源

核心 Apache-2.0（一次定死）。闭源层预留：技能市场（审核/签名/托管），见 `marketplace/`。

Apache-2.0
