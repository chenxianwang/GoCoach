# 一目弈镜 · 对局复盘 — Yimuyijing Go Review

> 把你的野狐 / LizzieYZY 对局，一键变成 KataGo 级别的复盘报告：胜负曲线、每手损失目数、大错集、终局形势估计、进步趋势——全部离线可看。
>
> Turn your Fox (野狐) / LizzieYZY games into a KataGo‑powered review: win‑rate curves, points‑lost‑per‑move, a blunder gallery, endgame territory estimates, and an improvement trend — all viewable offline.

<p align="center">
  <img src="docs/dashboard.png" alt="Dashboard" width="90%">
</p>

---

## 它解决什么问题 · Why

很多业余棋手能用 KataGo / LizzieYZY 分析单局，却很难看清**自己长期的棋力变化和反复犯的错误**。一目弈镜把多局对局聚合成一份可浏览的报告，告诉你：钱该花在哪——是布局、中盘还是官子，是某一类反复出现的漏招，还是最近到底有没有进步。

Amateurs can analyze a single game in KataGo, but rarely see their *long‑term* patterns. Yimuyijing aggregates many games into one browsable report that answers: where are you bleeding points, which mistakes recur, and are you actually improving?

## ✨ 功能 · Features

- **两种来源**：输入野狐 UID 自动下载并用云 KataGo（ikatago）分析；或直接**导入 LizzieYZY「已分析」SGF**（纯 Python 解析，无需再跑引擎）。
- **本地网页应用**：左侧栏列出全部报告（可删除、可折叠），右侧查看；支持「仅下载」「分析结果归入已有报告」「下载到指定文件夹」。
- **丰富的报告**：概览卡片、随时间的变化趋势（每手损失 / 大错率 / 每局大错数）、失误集（含相同漏招聚类）、逐局回顾、终局形势（目数）估计。
- **大错定义**：损失 ≥ 6 目 **或** 胜率下降 ≥ 15%。
- **进步趋势**：对比最近 N 局与之前 N 局的「每手平均损失目数」，给出 进步 / 持平 / 退步。
- **离线静态页**：自动生成 `index.html`，关掉程序也能浏览全部报告。
- **零第三方依赖**：纯 Python 标准库（分析功能需要本机 ikatago）。

## 🚀 快速开始 · Quickstart

**只想看看效果？** 直接打开 [`go_review/demo/review_report.html`](go_review/demo/review_report.html) —— 这是一份内置的示例报告（AlphaGo 对局），零配置即可浏览。

**完整使用：**

1. 安装 Python 3（macOS 自带或从 python.org 安装）。
2. 配置 ikatago（云 KataGo）凭据 —— 见下方「凭据」。
3. 启动：
   - macOS：双击仓库根目录的 **`一目弈镜.command`**，浏览器会自动打开 `http://127.0.0.1:8765`；
   - 或命令行：`python3 go_review/web_app.py`
4. 在「① 下载 + 分析」里填野狐 UID 开跑，或在「② 导入已分析 SGF」拖入 LizzieYZY 的已分析棋谱。

> 分析依赖本机的 ikatago。导入 LizzieYZY 已分析 SGF **不需要**引擎。

## 🔑 凭据 · Credentials

**不要把账号密码提交到 git。** 真正的设置放在 `go_review/config.json`（已被 `.gitignore` 忽略，仅存于本机）。仓库里只有模板 `go_review/config.example.json`。

首次使用，复制模板并填入你的 ikatago 路径/账号，或用环境变量：

```bash
cp go_review/config.example.json go_review/config.json
# 然后编辑 config.json，或：
export IKATAGO_USERNAME=你的账号
export IKATAGO_PASSWORD=你的密码
```

配置里字符串支持 `${ENV_VAR}` 与 `~` 展开，所以凭据可以只放在环境变量里、永不落盘。

## 🧠 工作原理 · How it works

```
野狐 UID ──下载──▶ SGF ──┐
                         ├─▶ KataGo(ikatago) 分析 ─┐
LizzieYZY 已分析 SGF ─────┘   (纯 Python 直接解析)   ├─▶ 每局 JSON ─▶ 聚合 ─▶ HTML 报告
                                                    ┘
```

- `sgfparse.py` 只取 SGF **主线**（分析谱里的分支变化不会被算进着手数）。
- `import_lizzie.py` 把 LizzieYZY 的 `LZ` / `LZOP` 内联分析解析成与引擎一致的 JSON：候选手、ownership、胜率（整数万分比，已正确归一化）。已落子的手从**落子后**的局面评估，与 LizzieYZY 自身的「差异手」吻合。
- `report.py` 把所有每局 JSON 聚合成单页 HTML，附带可按日期筛选的交互图表。
- `web_app.py` 是一个**纯标准库**的本地服务器（仪表盘 + 分析/导入面板 + 静态导出）。

## 🗂 项目结构 · Layout

```
go_review/
  web_app.py          本地网页应用（仪表盘 / 分析 / 导入 / 静态导出）
  pipeline.py         下载 → 写 config → 分析 → 报告 的串联
  analyze.py          调用 KataGo、生成每局 JSON
  import_lizzie.py    纯 Python 解析 LizzieYZY 已分析 SGF
  report.py           聚合并生成 HTML 报告
  sgfparse.py         轻量 SGF 解析（仅主线）
  estimate_score.py   终局形势（目数）估计
  appconfig.py        安全的配置加载（env 展开 / 示例回退）
  config.example.json 配置模板（无密钥）
  demo/               内置示例报告（可直接打开）
  tests/              解析核心的单元测试
一目弈镜.command       macOS 一键启动
```

## ✅ 测试 · Tests

```bash
python3 go_review/tests/test_parsing.py
# 或：python3 -m pytest go_review/tests
```

覆盖：胜率归一化、主线解析（忽略分支变化）、坐标转换、LZ 候选解析。

## 🛠 技术 · Tech

Python 3 标准库（`http.server`、`re`、`json` …），零 pip 依赖；前端为内联 HTML/CSS/JS（图表为手写 SVG）。分析后端为开源 [KataGo](https://github.com/lightvector/KataGo)，经 ikatago 云端调用。

## 📄 License

MIT — see [LICENSE](LICENSE).

## 🙏 致谢 · Acknowledgements

KataGo (lightvector)、LizzieYZF/LizzieYZY、野狐围棋。本项目与上述方均无官方关联。
