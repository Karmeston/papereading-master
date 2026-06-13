# Papereading Master Beta

[简体中文](README.md) | [English](README.en.md)

Papereading Master Beta 是一个本地优先的论文、代码与科研实验辅助 Agent。它不是聊天壳：系统会规划任务、调用检索与分析工具、验证引用和论文-代码对应关系，并在证据不足时自动改写查询重试。

> 当前版本：`0.2.0-beta.1`。项目处于 Beta 阶段，实验建议和代码对应检查仍需研究者最终确认。

## 主要能力

- 论文阅读：PDF 原文阅读、真实页码进度、文本选择与翻译、Markdown 笔记。
- 智能阅读：按摘要、引言、方法、实验、结果与结论分区检索后综合回答。
- 证据检索：返回可定位的原文句子、页码与引用，并突出最相关内容。
- 图表理解：定位 Figure、Table、Equation 和 Algorithm，支持缩略图、局部裁剪调整与视觉模型解释。
- 代码工作区：导入文件夹或 Jupyter Notebook，以目录树和语法高亮展示；支持简略或详细解析。
- 科研辅助：按任务保存论文和代码选择，发现相关论文，比较创新点、相关性与不足。
- 论文-代码核查：先从论文抽取可验证要求，再检索代码，最后由独立验证步骤检查双方证据。
- 实验辅助：生成可交给 Codex 等执行 Agent 的实验提示词，接收 Markdown 或图片结果并给出继续、调整或中止建议。
- Agent 编排：统一 Task Orchestrator、工具注册表以及 `PLAN -> EXECUTE -> VERIFY -> COMPLETE` 状态循环。
- 失败恢复：开放式问答检索不到证据或引用验证失败时，自动改写查询并重试一次。

## Windows 安装

从 GitHub Releases 下载：

```text
Papereading-Master-Beta-Setup-0.2.0-beta.1.exe
```

安装后从开始菜单启动 `Papereading Master Beta`。程序数据默认保存在：

```text
%LOCALAPPDATA%\PapereadingMasterBeta
```

卸载程序不会删除论文、笔记、设置或 API Key。Windows 10/11 通常已包含 Microsoft Edge WebView2 Runtime；若窗口无法显示，请先安装 WebView2 Runtime。

首次启动后，在“设置”中分别配置：

- 文字模型：提供商、模型名、Base URL、API Key。
- 视觉模型：OpenAI-compatible 视觉模型、Base URL、API Key。
- 输出语言：中文或英文，模型回答与界面同步切换。

远程端点必须填写 API Key；本机 `localhost` / `127.0.0.1` 兼容端点可不填写。程序不会内置或上传任何 API Key。

## 从源码运行

需要 Python 3.10+。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,desktop]"
.\.venv\Scripts\paper-agent.exe ui --port 8766
```

打开 `http://127.0.0.1:8766/`，或者启动桌面窗口：

```powershell
.\.venv\Scripts\paper-agent-desktop.exe
```

也可以复制 `.env.example` 为 `.env` 后手工配置。界面设置会写入同一配置文件。

## Embedding

Embedding 默认关闭：

## 常用 CLI

```powershell
paper-agent ingest .\paper.pdf --type paper
paper-agent ingest .\repository --type code
paper-agent list
paper-agent remove <document-id>
paper-agent search "speculative decoding acceptance rate"
paper-agent analyze --title "Target Paper"
paper-agent related "speculative decoding" --limit 8
paper-agent read --title "Target Paper"
paper-agent explain "Figure 2" --title "Target Paper"
paper-agent runs --limit 10
paper-agent chat "总结方法与实验结论，并保留引用"
```

兼容入口 `finals-agent` 仍然可用。

## 数据与隐私

- 论文、代码、索引、笔记和任务状态均保存在本机。
- 只有调用外部文字或视觉模型时，相关提示词和必要上下文会发送到用户配置的 API。
- 代码解析只读，不执行导入的项目代码。
- API Key 保存在应用数据目录的 `.env` 中，不进入日志和接口响应。
- `data/`、`.env`、构建产物和调试截图已被 `.gitignore` 排除。

论文-代码对应报告会明确标注代码扫描覆盖范围。只有独立验证通过的双方证据才会被标记为已验证；扫描不完整时，“未找到实现”只会判定为不确定，不会被当作缺失事实。

## License

[MIT](LICENSE)
