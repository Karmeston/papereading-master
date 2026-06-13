# Papereading Master Beta

[简体中文](README.md) | [English](README.en.md)

Papereading Master Beta is a local-first agent for reading papers, inspecting code, and assisting research experiments. It plans tasks, invokes retrieval and analysis tools, verifies citations and paper-code correspondence, and automatically rewrites a query once when evidence is insufficient.

> Current version: `0.2.0-beta.1`. This project is in beta. Research suggestions and paper-code correspondence reports still require final review by the researcher.

## Features

- Paper reading: PDF viewer, page-based reading progress, text selection and translation, and Markdown notes.
- Intelligent reading: section-aware retrieval and synthesis across the abstract, introduction, methods, experiments, results, and conclusion.
- Evidence retrieval: locatable source sentences with page numbers and citations, with the most relevant text highlighted.
- Figure understanding: detects figures, tables, equations, and algorithms; supports thumbnails, adjustable crops, and vision-model explanations.
- Code workspace: imports folders and Jupyter Notebooks, with a file tree, syntax highlighting, and concise or detailed analysis.
- Research assistant: stores paper and code selections per task, discovers related papers, and compares novelty, relevance, and limitations.
- Paper-code verification: extracts verifiable requirements from papers, searches the codebase, and independently verifies evidence from both sides.
- Experiment assistance: generates detailed prompts for execution agents such as Codex, accepts Markdown or image results, and recommends whether to continue, adjust, or stop.
- Agent orchestration: unified Task Orchestrator, tool registry, and `PLAN -> EXECUTE -> VERIFY -> COMPLETE` state loop.
- Failure recovery: automatically rewrites and retries once when open-ended retrieval finds no evidence or citation verification fails.

## Windows Installation

Download the installer from GitHub Releases:

```text
Papereading-Master-Beta-Setup-0.2.0-beta.1.exe
```

Launch `Papereading Master Beta` from the Start menu after installation. Application data is stored in:

```text
%LOCALAPPDATA%\PapereadingMasterBeta
```

Uninstalling the application does not remove papers, notes, settings, or API keys. Windows 10 and 11 usually include Microsoft Edge WebView2 Runtime. Install WebView2 Runtime first if the application window cannot render.

Configure these options under Settings after the first launch:

- Text model: provider, model name, Base URL, and API key.
- Vision model: OpenAI-compatible vision model, Base URL, and API key.
- Output language: Chinese or English for both the interface and model responses.

Remote endpoints require an API key. Local `localhost` and `127.0.0.1` compatible endpoints may omit it. The application does not bundle or upload API keys.

## Run from Source

Python 3.10 or later is required.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,desktop]"
.\.venv\Scripts\paper-agent.exe ui --port 8766
```

Open `http://127.0.0.1:8766/`, or launch the desktop window:

```powershell
.\.venv\Scripts\paper-agent-desktop.exe
```

You can also copy `.env.example` to `.env` and configure it manually. Settings saved in the interface are written to the same file.

## Embeddings

Embeddings are disabled by default.

## Common CLI Commands

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
paper-agent chat "Summarize the methods and experimental findings with citations."
```

The legacy `finals-agent` command remains available.

## Data and Privacy

- Papers, code, indexes, notes, and task state remain on the local machine.
- Only prompts and necessary context are sent to user-configured APIs when external text or vision models are invoked.
- Imported code is read-only and is never executed.
- API keys are stored in `.env` under the application data directory and are excluded from logs and API responses.
- `data/`, `.env`, build artifacts, and debug screenshots are excluded through `.gitignore`.

Paper-code correspondence reports state their code-scanning coverage. A claim is marked as verified only when independent checks pass for evidence from both the paper and code. When the scan is incomplete, a missing match is treated as uncertain rather than proof that an implementation is absent.

## License

[MIT](LICENSE)
