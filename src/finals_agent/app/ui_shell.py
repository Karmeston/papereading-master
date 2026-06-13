APP_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Papereading Master Beta</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.11.1/build/styles/github-dark.min.css">
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.11.1/build/highlight.min.js"></script>
  <style>
    :root {
      color-scheme: light;
      --canvas: #f3f5f6;
      --surface: #ffffff;
      --surface-alt: #f8f9fa;
      --line: #dde2e5;
      --line-strong: #c9d0d4;
      --text: #172026;
      --muted: #67737b;
      --accent: #176b67;
      --accent-soft: #e3f0ee;
      --blue: #3b5f8a;
      --warning: #a86416;
      --danger: #a43d3d;
      --success: #28784a;
      --topbar: 52px;
      font-family: Inter, "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
    }
    * { box-sizing: border-box; }
    [hidden] { display: none !important; }
    html, body { height: 100%; }
    body {
      margin: 0;
      overflow: hidden;
      background: var(--canvas);
      color: var(--text);
      font-size: 14px;
      letter-spacing: 0;
    }
    button, input, select, textarea { font: inherit; letter-spacing: 0; }
    button { cursor: pointer; }
    button:disabled { cursor: wait; opacity: .55; }
    .topbar {
      height: var(--topbar);
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 0 14px;
      background: #20282d;
      color: #fff;
      border-bottom: 1px solid #151b1f;
    }
    .brand {
      width: 270px;
      display: flex;
      align-items: center;
      gap: 10px;
      flex: 0 0 auto;
      font-weight: 700;
    }
    .brand-mark {
      width: 28px;
      height: 28px;
      display: grid;
      place-items: center;
      background: #dcebe8;
      color: #184b49;
      border-radius: 6px;
      font-family: Georgia, serif;
      font-size: 17px;
    }
    .top-title {
      min-width: 0;
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: #d8dee2;
      font-size: 13px;
    }
    .connection {
      display: flex;
      align-items: center;
      gap: 6px;
      color: #b9c3c8;
      font-size: 12px;
    }
    .connection::before {
      content: "";
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #58b981;
    }
    .top-command {
      min-height: 32px;
      padding: 0 11px;
      border: 1px solid #4a565d;
      border-radius: 6px;
      background: #2b353b;
      color: #f3f6f7;
      font-size: 12px;
      white-space: nowrap;
    }
    .top-command:hover { border-color: #708087; background: #354148; }
    .workspace-switch {
      display: inline-flex;
      padding: 3px;
      border-radius: 6px;
      background: #151c20;
    }
    .workspace-tab {
      min-height: 30px;
      padding: 0 11px;
      border: 0;
      border-radius: 4px;
      background: transparent;
      color: #aeb9be;
      font-size: 12px;
    }
    .workspace-tab.active { background: #3a474e; color: #fff; }
    .icon-btn {
      width: 32px;
      height: 32px;
      display: inline-grid;
      place-items: center;
      flex: 0 0 auto;
      padding: 0;
      border: 1px solid transparent;
      border-radius: 6px;
      background: transparent;
      color: inherit;
      font-size: 18px;
      line-height: 1;
    }
    .icon-btn:hover { background: rgba(255,255,255,.1); }
    .shell {
      height: calc(100vh - var(--topbar));
      display: grid;
      grid-template-columns: 248px minmax(420px, 1fr) 270px;
      min-width: 0;
    }
    .shell.code-mode { grid-template-columns: 248px minmax(420px, 1fr) 280px; }
    .shell.code-mode #inspector-artifacts { display: none; }
    .shell.code-mode .inspector-tabs { grid-template-columns: 1fr; }
    .shell.code-mode [data-inspector-panel="artifacts"] { display: none; }
    .library, .inspector, .workspace { min-width: 0; min-height: 0; }
    .library {
      display: flex;
      flex-direction: column;
      background: #eef1f2;
      border-right: 1px solid var(--line);
    }
    .side-head {
      height: 54px;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 0 12px;
      border-bottom: 1px solid var(--line);
    }
    .side-head strong { flex: 1; font-size: 13px; }
    .side-head .icon-btn { color: var(--muted); }
    .side-head .icon-btn:hover { background: #dfe4e6; color: var(--text); }
    .library-search { padding: 10px 10px 6px; }
    .library-controls {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 6px;
      padding: 0 10px 7px;
    }
    .library-controls select {
      width: 100%;
      height: 32px;
      min-width: 0;
      padding: 0 7px;
      border: 1px solid var(--line-strong);
      border-radius: 5px;
      background: var(--surface);
      color: var(--text);
      font-size: 11px;
    }
    .field {
      width: 100%;
      min-width: 0;
      height: 36px;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      padding: 0 10px;
      outline: none;
      background: var(--surface);
      color: var(--text);
    }
    .field:focus, textarea:focus, select:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 2px rgba(23,107,103,.12);
    }
    textarea.field { height: auto; min-height: 84px; padding: 9px 10px; resize: vertical; }
    .doc-count {
      padding: 4px 12px 7px;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
    }
    .doc-list { flex: 1; overflow: auto; padding-bottom: 12px; }
    .doc-group-label {
      position: sticky;
      top: 0;
      z-index: 2;
      padding: 7px 12px 5px;
      background: #edf0f1;
      color: var(--muted);
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .doc-entry { position: relative; }
    .doc {
      width: 100%;
      display: block;
      padding: 11px 38px 10px 15px;
      border: 0;
      border-left: 3px solid transparent;
      background: transparent;
      color: var(--text);
      text-align: left;
    }
    .doc:hover { background: #e4e8ea; }
    .doc.active { background: var(--surface); border-left-color: var(--accent); }
    .doc-more {
      position: absolute;
      top: 8px;
      right: 7px;
      width: 28px;
      height: 28px;
      border: 0;
      border-radius: 4px;
      background: transparent;
      color: var(--muted);
      font-size: 18px;
      line-height: 1;
    }
    .doc-entry:hover .doc-more, .doc-more.active { background: #d8dee1; color: var(--text); }
    .doc-menu {
      position: absolute;
      top: 36px;
      right: 8px;
      z-index: 8;
      width: 126px;
      padding: 4px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface);
      box-shadow: 0 7px 20px rgba(25,35,40,.18);
    }
    .doc-menu button {
      width: 100%;
      min-height: 31px;
      padding: 0 8px;
      border: 0;
      border-radius: 4px;
      background: transparent;
      color: var(--text);
      text-align: left;
      font-size: 12px;
    }
    .doc-menu button:hover { background: var(--surface-alt); }
    .doc-menu button.danger { color: var(--danger); }
    .doc-title {
      display: -webkit-box;
      overflow: hidden;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
      font-weight: 650;
      line-height: 1.4;
    }
    .doc-meta {
      margin-top: 5px;
      overflow: hidden;
      color: var(--muted);
      font-size: 11px;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .doc-flags { display: inline-flex; gap: 4px; margin-right: 4px; }
    .doc-flag {
      padding: 1px 4px;
      border-radius: 3px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 9px;
      font-weight: 700;
    }
    .doc-flag.archived { background: #e8eaeb; color: var(--muted); }
    .workspace {
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto;
      background: var(--canvas);
    }
    .document-head {
      background: var(--surface);
      border-bottom: 1px solid var(--line);
    }
    .document-title-row {
      min-height: 58px;
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 8px 16px;
    }
    .document-title { min-width: 0; flex: 1; }
    .document-title h1 {
      margin: 0;
      overflow: hidden;
      font-size: 16px;
      font-weight: 680;
      line-height: 1.35;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .document-title p {
      margin: 3px 0 0;
      overflow: hidden;
      color: var(--muted);
      font-size: 11px;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .danger-icon { color: var(--danger); }
    .mode-tabs {
      display: flex;
      gap: 4px;
      padding: 0 12px;
      overflow-x: auto;
    }
    .mode-tab {
      height: 36px;
      padding: 0 11px;
      border: 0;
      border-bottom: 2px solid transparent;
      background: transparent;
      color: var(--muted);
      white-space: nowrap;
    }
    .mode-tab:hover { color: var(--text); }
    .mode-tab.active { border-bottom-color: var(--accent); color: var(--accent); font-weight: 650; }
    .work-area { min-height: 0; overflow: hidden; }
    .view { display: none; height: 100%; min-height: 0; }
    .view.active { display: block; }
    .source-view.active { display: grid; grid-template-rows: 44px minmax(0, 1fr); }
    .source-view.active.no-toolbar { grid-template-rows: minmax(0, 1fr); }
    .source-toolbar {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 7px;
      padding: 6px 12px;
      border-bottom: 1px solid var(--line);
      background: var(--surface);
    }
    .source-toolbar .icon-btn { color: var(--text); border-color: var(--line); }
    .page-jump {
      width: 62px;
      height: 30px;
      padding: 0 7px;
      border: 1px solid var(--line-strong);
      border-radius: 5px;
      text-align: center;
    }
    .page-total { min-width: 46px; color: var(--muted); font-size: 12px; }
    .pdf-reader {
      height: 100%;
      overflow: auto;
      padding: 20px 24px 60px;
      background: #697176;
      scroll-behavior: smooth;
    }
    .pdf-page {
      position: relative;
      width: min(920px, 100%);
      margin: 0 auto 18px;
      background: #fff;
      box-shadow: 0 2px 9px rgba(0,0,0,.28);
    }
    .pdf-page img {
      width: 100%;
      height: auto;
      display: block;
      user-select: none;
    }
    .pdf-text-layer {
      position: absolute;
      inset: 0;
      z-index: 2;
      overflow: hidden;
      color: transparent;
      user-select: text;
      cursor: text;
    }
    .pdf-text-line {
      position: absolute;
      display: block;
      overflow: hidden;
      color: transparent;
      font-family: Arial, sans-serif;
      white-space: pre;
      line-height: 1;
      transform-origin: left top;
      user-select: text;
    }
    .pdf-text-line::selection { background: rgba(59,95,138,.32); color: transparent; }
    .pdf-translation {
      position: absolute;
      z-index: 4;
      min-width: 260px;
      max-width: calc(100% - 16px);
      max-height: 320px;
      display: grid;
      grid-template-rows: 34px minmax(0, 1fr);
      border: 1px solid #b9c2c7;
      border-radius: 6px;
      background: rgba(255,255,255,.98);
      color: #172026;
      box-shadow: 0 8px 24px rgba(17,26,31,.24);
      overflow: hidden;
      user-select: text;
    }
    .pdf-translation-head {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 0 7px 0 11px;
      border-bottom: 1px solid #dde2e5;
      background: #f5f7f8;
      font-size: 11px;
      font-weight: 700;
    }
    .pdf-translation-head span { flex: 1; }
    .pdf-translation-body {
      min-height: 46px;
      overflow: auto;
      padding: 10px 12px 12px;
      font-size: 13px;
      line-height: 1.65;
      overflow-wrap: anywhere;
    }
    .pdf-translation-body p { margin: 0 0 8px; }
    .pdf-translation-body p:last-child { margin-bottom: 0; }
    .pdf-translation-cursor {
      display: inline-block;
      width: 2px;
      height: 1em;
      margin-left: 2px;
      background: var(--accent);
      vertical-align: -2px;
      animation: blink 1s steps(1) infinite;
    }
    .pdf-page-number {
      position: absolute;
      right: 8px;
      bottom: 7px;
      padding: 3px 7px;
      border-radius: 4px;
      background: rgba(20,27,31,.72);
      color: #fff;
      font-size: 11px;
      pointer-events: none;
    }
    .text-paper {
      height: 100%;
      max-width: 860px;
      margin: 0 auto;
      overflow: auto;
      padding: 42px 54px 70px;
      background: var(--surface);
      white-space: pre-wrap;
      line-height: 1.75;
    }
    .markdown-workspace {
      height: 100%;
      min-height: 0;
      display: grid;
      grid-template-rows: 42px minmax(0, 1fr);
      background: var(--surface);
    }
    .markdown-toolbar {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 5px 10px;
      border-bottom: 1px solid var(--line);
      background: var(--surface-alt);
    }
    .markdown-toolbar .spacer { flex: 1; }
    .save-state { color: var(--muted); font-size: 11px; }
    .markdown-editor {
      width: 100%;
      height: 100%;
      resize: none;
      border: 0;
      outline: 0;
      padding: 28px 34px 70px;
      background: #1e1e1e;
      color: #d4d4d4;
      font: 13px/1.65 Consolas, "Cascadia Code", monospace;
      tab-size: 2;
    }
    .markdown-preview {
      height: 100%;
      max-width: 880px;
      margin: 0 auto;
      overflow: auto;
      padding: 30px 38px 70px;
      line-height: 1.75;
    }
    .markdown-preview h1, .markdown-preview h2, .markdown-preview h3 { margin: 22px 0 10px; }
    .markdown-preview h1 { font-size: 26px; }
    .markdown-preview h2 { font-size: 20px; }
    .markdown-preview h3 { font-size: 16px; }
    .markdown-preview pre { overflow: auto; padding: 13px; border-radius: 5px; background: #1e1e1e; color: #d4d4d4; }
    .markdown-preview code { font-family: Consolas, monospace; }
    .code-workspace {
      height: 100%;
      min-height: 0;
      display: grid;
      grid-template-columns: 220px minmax(0, 1fr);
      background: #1e1e1e;
      color: #d4d4d4;
    }
    .code-explorer {
      min-width: 0;
      overflow: auto;
      border-right: 1px solid #30343a;
      background: #181a1f;
    }
    .code-explorer-head {
      padding: 11px 12px 8px;
      color: #aeb4bc;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .code-tree-item {
      width: 100%;
      height: 29px;
      display: flex;
      align-items: center;
      gap: 6px;
      padding-right: 8px;
      border: 0;
      background: transparent;
      color: #c7ccd2;
      text-align: left;
      font: 12px Consolas, monospace;
      white-space: nowrap;
    }
    .code-tree-item:hover { background: #25282e; }
    .code-tree-item.active { background: #30343b; color: #fff; }
    .code-tree-icon { width: 15px; color: #d7b85a; text-align: center; }
    .code-editor { min-width: 0; min-height: 0; display: grid; grid-template-rows: 36px minmax(0, 1fr); }
    .code-tab {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 0 13px;
      border-bottom: 1px solid #30343a;
      background: #21242a;
      color: #cfd3d8;
      font: 12px Consolas, monospace;
    }
    .code-tab-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .code-tab-action {
      min-height: 26px;
      padding: 0 8px;
      border: 1px solid #454b54;
      border-radius: 4px;
      background: #2b2f36;
      color: #d7dbe0;
      font: 11px sans-serif;
    }
    .code-content { min-width: 0; overflow: auto; background: #1e1e1e; }
    .code-content pre { min-width: max-content; margin: 0; padding: 16px 18px 60px; background: transparent; }
    .code-content code { font: 13px/1.62 Consolas, "Cascadia Code", monospace; tab-size: 4; }
    .notebook-view { max-width: 980px; margin: 0 auto; padding: 18px 22px 70px; }
    .notebook-cell {
      display: grid;
      grid-template-columns: 54px minmax(0, 1fr);
      margin-bottom: 13px;
    }
    .notebook-prompt { padding: 11px 8px 0 0; color: #7fa5d8; font: 11px Consolas, monospace; text-align: right; }
    .notebook-cell-body { min-width: 0; border-left: 2px solid #3b4048; background: #202329; }
    .notebook-cell.markdown .notebook-cell-body { padding: 13px 15px; background: #25282e; color: #d8dce1; line-height: 1.65; white-space: pre-wrap; }
    .notebook-cell.markdown h1, .notebook-cell.markdown h2, .notebook-cell.markdown h3 { margin: 0 0 9px; color: #f0f2f4; }
    .notebook-cell.markdown h1 { font-size: 21px; }
    .notebook-cell.markdown h2 { font-size: 17px; }
    .notebook-cell.markdown h3 { font-size: 14px; }
    .notebook-cell.markdown p { margin: 0 0 9px; }
    .notebook-cell.markdown ul { margin: 0 0 9px; padding-left: 20px; }
    .notebook-cell pre { margin: 0; padding: 13px 15px; overflow: auto; }
    .notebook-output { padding: 10px 15px; border-top: 1px solid #343941; color: #c9cdd2; white-space: pre-wrap; font: 12px/1.55 Consolas, monospace; }
    .empty {
      height: 100%;
      display: grid;
      place-items: center;
      padding: 30px;
      color: var(--muted);
      text-align: center;
    }
    .empty strong { display: block; margin-bottom: 6px; color: var(--text); font-size: 16px; }
    .tool-view { height: 100%; overflow: auto; background: var(--surface); }
    .tool-bar {
      position: sticky;
      top: 0;
      z-index: 2;
      display: flex;
      gap: 8px;
      align-items: center;
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
      background: rgba(255,255,255,.96);
    }
    .tool-bar .field { flex: 1; }
    .btn {
      min-height: 36px;
      padding: 0 13px;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      background: var(--surface);
      color: var(--text);
      white-space: nowrap;
    }
    .btn:hover { background: var(--surface-alt); border-color: #aeb8bd; }
    .btn.primary { border-color: var(--accent); background: var(--accent); color: #fff; }
    .btn.primary:hover { background: #125b58; }
    .btn.danger { color: var(--danger); }
    .output { max-width: 900px; margin: 0 auto; padding: 18px 22px 72px; }
    .output-title { margin: 0 0 14px; font-size: 16px; }
    .coverage {
      display: flex;
      gap: 14px;
      align-items: center;
      padding: 11px 12px;
      border: 1px solid var(--line);
      border-left: 3px solid var(--accent);
      background: var(--surface-alt);
    }
    .coverage strong { font-size: 18px; }
    .coverage span { color: var(--muted); font-size: 12px; }
    .section-block { padding: 16px 2px; border-bottom: 1px solid var(--line); }
    .section-block:last-child { border-bottom: 0; }
    .analysis-text { line-height: 1.75; white-space: pre-wrap; }
    .stream-status { margin: 14px 0; color: var(--muted); font-size: 12px; }
    .stream-report { line-height: 1.82; white-space: pre-wrap; overflow-wrap: anywhere; }
    .stream-report h3 { margin: 22px 0 8px; font-size: 15px; }
    .stream-report p { margin: 0 0 12px; }
    .stream-cursor {
      display: inline-block;
      width: 7px;
      height: 16px;
      margin-left: 3px;
      background: var(--accent);
      vertical-align: -2px;
      animation: blink 1s steps(1) infinite;
    }
    @keyframes blink { 50% { opacity: 0; } }
    .section-heading { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
    .section-heading h3 { margin: 0; font-size: 14px; }
    .tag {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 7px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--surface);
      color: var(--muted);
      font-size: 11px;
    }
    .tag.ok { border-color: #b8d8c5; background: #edf7f1; color: var(--success); }
    .tag.warn { border-color: #e0caab; background: #fbf5eb; color: var(--warning); }
    .evidence {
      margin-top: 9px;
      padding-left: 11px;
      border-left: 2px solid #ced7dc;
      line-height: 1.6;
    }
    .citation { margin-top: 4px; color: var(--blue); font-size: 11px; overflow-wrap: anywhere; }
    .muted { color: var(--muted); }
    .result { padding: 14px 2px; border-bottom: 1px solid var(--line); }
    .result:last-child { border-bottom: 0; }
    .result-title { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 6px; font-weight: 650; }
    .result p { margin: 0; line-height: 1.65; }
    .result-reason { margin: 7px 0; color: var(--muted); font-size: 12px; }
    .search-intent {
      display: grid;
      gap: 4px;
      margin-bottom: 16px;
      padding: 10px 12px;
      border-left: 3px solid var(--accent);
      background: var(--surface-alt);
      line-height: 1.55;
    }
    .search-intent strong { font-size: 12px; }
    .search-intent span { color: var(--muted); }
    .answer { white-space: pre-wrap; line-height: 1.72; overflow-wrap: anywhere; }
    .composer {
      padding: 10px 14px 12px;
      border-top: 1px solid var(--line);
      background: var(--surface);
    }
    .messages { display: none; max-height: 210px; overflow: auto; padding: 8px 2px 10px; }
    .messages.visible { display: block; }
    .message { max-width: 88%; margin: 7px 0; padding: 9px 11px; border-radius: 7px; line-height: 1.55; }
    .message.user { margin-left: auto; background: var(--accent-soft); }
    .message.assistant { border: 1px solid var(--line); background: var(--surface-alt); }
    .message-content { overflow-wrap: anywhere; }
    .message-content p { margin: 0 0 8px; }
    .message-content p:last-child { margin-bottom: 0; }
    .message-content pre { overflow: auto; padding: 9px; border-radius: 5px; background: #20282d; color: #f3f5f6; }
    .message-content code { font-family: Consolas, monospace; }
    .message-content .katex-display { overflow-x: auto; overflow-y: hidden; padding: 4px 0; }
    .compose-row { display: flex; align-items: flex-end; gap: 8px; }
    .compose-row textarea {
      flex: 1;
      min-height: 38px;
      max-height: 120px;
      resize: none;
      padding-top: 8px;
    }
    .send-btn { width: 38px; height: 38px; padding: 0; font-size: 17px; }
    .inspector {
      display: flex;
      flex-direction: column;
      overflow: auto;
      border-left: 1px solid var(--line);
      background: var(--surface);
    }
    .inspector-section { padding: 14px; border-bottom: 1px solid var(--line); }
    .section-label {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 11px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .progress-slider {
      width: 100%;
      height: 22px;
      margin: 2px 0 7px;
      accent-color: var(--accent);
      cursor: pointer;
    }
    .reading-progress-track {
      height: 7px;
      overflow: hidden;
      border-radius: 4px;
      background: #dfe4e6;
    }
    .reading-progress-fill { height: 100%; width: 0; background: var(--accent); transition: width .18s ease; }
    .reading-page-label { margin-top: 9px; color: var(--muted); font-size: 12px; }
    .artifact-section { flex: 1; min-height: 0; display: flex; flex-direction: column; }
    .artifact-list { min-height: 120px; overflow: auto; }
    .artifact-item {
      width: 100%;
      display: grid;
      grid-template-columns: 72px minmax(0, 1fr);
      gap: 9px;
      align-items: center;
      padding: 9px 0;
      border: 0;
      border-bottom: 1px solid #edf0f2;
      background: transparent;
      color: var(--text);
      text-align: left;
    }
    .artifact-item:hover { color: var(--accent); background: #f7f9f9; }
    .artifact-thumb {
      width: 72px;
      height: 56px;
      display: block;
      object-fit: contain;
      border: 1px solid var(--line);
      border-radius: 4px;
      background: #fff;
    }
    .artifact-item-copy { min-width: 0; }
    .artifact-item strong { display: block; overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
    .artifact-item span {
      display: -webkit-box;
      margin-top: 3px;
      overflow: hidden;
      color: var(--muted);
      font-size: 11px;
      line-height: 1.35;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
    }
    .inspector-tabs {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 3px;
      margin: 10px 12px 0;
      padding: 3px;
      border-radius: 6px;
      background: #eef1f2;
    }
    .inspector-tab {
      min-height: 31px;
      border: 0;
      border-radius: 4px;
      background: transparent;
      color: var(--muted);
    }
    .inspector-tab.active { background: var(--surface); color: var(--text); box-shadow: 0 1px 2px rgba(25,35,40,.12); font-weight: 650; }
    .inspector-panel { display: none; min-height: 0; flex: 1; }
    .inspector-panel.active { display: flex; flex-direction: column; }
    .digest-list {
      padding: 2px 0;
      color: var(--text);
      font-size: 12px;
      line-height: 1.65;
      white-space: pre-wrap;
    }
    .digest-actions { display: flex; gap: 6px; margin-bottom: 10px; }
    .digest-actions .btn { flex: 1; }
    .note-composer { display: grid; gap: 7px; margin-bottom: 10px; }
    .note-composer textarea {
      width: 100%;
      min-height: 90px;
      resize: vertical;
      border: 1px solid var(--line-strong);
      border-radius: 5px;
      padding: 8px;
      outline: none;
      font: 12px/1.55 Consolas, monospace;
    }
    .note-composer-actions { display: flex; justify-content: flex-end; gap: 6px; }
    .segmented { display: inline-flex; padding: 3px; border-radius: 6px; background: #e8edef; }
    .segment {
      min-height: 29px;
      padding: 0 10px;
      border: 0;
      border-radius: 4px;
      background: transparent;
      color: var(--muted);
      font-size: 12px;
    }
    .segment.active { background: #fff; color: var(--text); box-shadow: 0 1px 2px rgba(20,30,35,.15); }
    .digest-entry {
      width: 100%;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 4px 6px;
      min-height: 58px;
      padding: 10px 2px;
      border-bottom: 1px solid #edf0f2;
      background: transparent;
      color: var(--text);
      font-size: 12px;
      line-height: 1.45;
    }
    .digest-entry.dragging { opacity: .45; }
    .digest-entry.drop-target { border-top: 2px solid var(--accent); }
    .digest-open {
      min-width: 0;
      display: grid;
      gap: 5px;
      grid-row: 1 / span 3;
      padding: 0;
      border: 0;
      background: transparent;
      color: inherit;
      text-align: left;
    }
    .digest-entry-actions { display: flex; align-items: flex-start; gap: 2px; }
    .digest-entry-action {
      width: 25px;
      height: 25px;
      display: grid;
      place-items: center;
      padding: 0;
      border: 0;
      border-radius: 4px;
      background: transparent;
      color: var(--muted);
      font-size: 14px;
    }
    .digest-entry-action:hover { background: #edf1f2; color: var(--text); }
    .digest-entry-action.delete:hover { color: var(--danger); }
    .digest-drag { cursor: grab; }
    .digest-entry-head { display: flex; align-items: baseline; gap: 7px; min-width: 0; }
    .digest-entry-kind { flex: 0 0 auto; color: var(--accent); font-size: 11px; font-weight: 700; }
    .digest-entry-title {
      min-width: 0;
      overflow: hidden;
      color: var(--text);
      font-size: 12px;
      font-weight: 600;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .digest-entry-preview {
      display: -webkit-box;
      overflow: hidden;
      color: #344047;
      font-size: 13px;
      line-height: 1.5;
      overflow-wrap: anywhere;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
    }
    .digest-entry-time { color: var(--muted); font-size: 10px; line-height: 1.3; }
    .digest-entry:hover { color: var(--accent); }
    .digest-entry:last-child { border-bottom: 0; }
    .digest-empty { color: var(--muted); font-size: 12px; line-height: 1.6; }
    .evidence-highlight { font-weight: 750; color: var(--text); }
    .floating-layer { position: fixed; inset: 0; z-index: 40; pointer-events: none; }
    .artifact-window {
      position: absolute;
      top: 90px;
      left: 310px;
      width: min(620px, calc(100vw - 40px));
      height: min(650px, calc(100vh - 90px));
      min-width: 340px;
      min-height: 260px;
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: 42px minmax(0, 1fr);
      overflow: hidden;
      resize: both;
      border: 1px solid var(--line-strong);
      border-radius: 7px;
      background: var(--surface);
      box-shadow: 0 16px 45px rgba(12,22,28,.24);
      pointer-events: auto;
    }
    .artifact-window-head {
      min-width: 0;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 0 8px 0 12px;
      border-bottom: 1px solid var(--line);
      background: #f3f5f6;
      cursor: move;
      user-select: none;
    }
    .artifact-window-head strong { min-width: 0; flex: 1; overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
    .artifact-window-head .btn { min-height: 28px; padding: 0 9px; flex: 0 0 auto; font-size: 12px; }
    .artifact-window-body { min-width: 0; min-height: 0; overflow: auto; padding: 12px; }
    .artifact-explanation { margin-top: 12px; white-space: pre-wrap; line-height: 1.65; }
    .crop-stage {
      position: relative;
      max-width: 100%;
      margin: 0 auto;
      overflow: hidden;
      border: 1px solid var(--line);
      background: #fff;
      cursor: default;
      user-select: none;
    }
    .crop-stage img {
      position: absolute;
      max-width: none;
      display: block;
      pointer-events: none;
    }
    .crop-selection {
      position: absolute;
      inset: 0;
      border: 2px solid #18a197;
      background: transparent;
      cursor: move;
      pointer-events: auto;
    }
    .crop-handle {
      position: absolute;
      width: 10px;
      height: 10px;
      border: 2px solid #fff;
      border-radius: 2px;
      background: var(--accent);
      box-shadow: 0 1px 3px rgba(0,0,0,.28);
    }
    .crop-handle[data-handle="nw"] { top: 1px; left: 1px; cursor: nwse-resize; }
    .crop-handle[data-handle="n"] { top: 1px; left: calc(50% - 5px); cursor: ns-resize; }
    .crop-handle[data-handle="ne"] { top: 1px; right: 1px; cursor: nesw-resize; }
    .crop-handle[data-handle="e"] { top: calc(50% - 5px); right: 1px; cursor: ew-resize; }
    .crop-handle[data-handle="se"] { right: 1px; bottom: 1px; cursor: nwse-resize; }
    .crop-handle[data-handle="s"] { bottom: 1px; left: calc(50% - 5px); cursor: ns-resize; }
    .crop-handle[data-handle="sw"] { bottom: 1px; left: 1px; cursor: nesw-resize; }
    .crop-handle[data-handle="w"] { top: calc(50% - 5px); left: 1px; cursor: ew-resize; }
    .crop-help { margin: 9px 0 0; color: var(--muted); font-size: 12px; }
    .settings-note { color: var(--muted); font-size: 12px; line-height: 1.5; }
    .settings-group { display: grid; gap: 9px; padding: 12px; border: 1px solid var(--line); border-radius: 6px; }
    .settings-group h3 { margin: 0 0 2px; font-size: 13px; }
    .settings-field { display: grid; gap: 5px; color: var(--muted); font-size: 11px; }
    .modal-backdrop {
      position: fixed;
      inset: 0;
      z-index: 20;
      display: none;
      place-items: center;
      padding: 20px;
      background: rgba(17,24,28,.46);
    }
    .modal-backdrop.open { display: grid; }
    .modal {
      width: min(520px, 100%);
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      background: var(--surface);
      box-shadow: 0 18px 50px rgba(15,25,30,.22);
    }
    .settings-modal {
      width: min(600px, 100%);
      max-height: calc(100vh - 40px);
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto;
      overflow: hidden;
    }
    .settings-modal .modal-body { min-height: 0; overflow-y: auto; overscroll-behavior: contain; }
    .research-workspace {
      height: calc(100vh - var(--topbar));
      display: grid;
      grid-template-rows: 58px minmax(0, 1fr);
      overflow: hidden;
      background: var(--surface);
    }
    .research-page-head {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 0 20px;
      border-bottom: 1px solid var(--line);
      background: var(--surface);
    }
    .research-page-head h1 { flex: 1; margin: 0; font-size: 17px; }
    .research-page-head p { margin: 0; color: var(--muted); font-size: 12px; }
    .research-attachment-picker {
      min-height: 70px;
      display: grid;
      place-items: center;
      padding: 12px;
      border: 1px dashed #aeb8bd;
      border-radius: 6px;
      background: var(--surface-alt);
      color: var(--muted);
      text-align: center;
      cursor: pointer;
    }
    .research-attachment-picker:hover { border-color: var(--accent); }
    .research-attachment-picker input { display: none; }
    .research-attachments { display: grid; gap: 7px; }
    .research-attachment {
      display: grid;
      grid-template-columns: 52px minmax(0, 1fr);
      gap: 9px;
      align-items: center;
      padding: 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface-alt);
    }
    .research-attachment img {
      width: 52px;
      height: 42px;
      object-fit: cover;
      border: 1px solid var(--line);
      border-radius: 4px;
      background: #fff;
    }
    .research-attachment-icon {
      width: 52px;
      height: 42px;
      display: grid;
      place-items: center;
      border-radius: 4px;
      background: #e8edef;
      color: var(--blue);
      font-weight: 700;
    }
    .research-attachment strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
    .research-attachment span { display: block; margin-top: 3px; color: var(--muted); font-size: 11px; }
    .research-body {
      min-width: 0;
      min-height: 0;
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
    }
    .research-setup {
      min-height: 0;
      overflow-y: auto;
      padding: 16px;
      border-right: 1px solid var(--line);
      background: var(--surface-alt);
    }
    .research-results { min-height: 0; overflow-y: auto; padding: 0 22px 40px; }
    .research-section { padding: 20px 0; border-bottom: 1px solid var(--line); }
    .research-section:last-child { border-bottom: 0; }
    .research-section-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
    .research-section-head h3 { flex: 1; margin: 0; font-size: 15px; }
    .research-form { display: grid; gap: 12px; }
    .research-choice-list {
      display: grid;
      gap: 5px;
      max-height: 190px;
      overflow: auto;
      padding: 6px 0;
    }
    .research-choice {
      display: grid;
      grid-template-columns: 18px minmax(0, 1fr);
      gap: 7px;
      align-items: start;
      padding: 6px 4px;
      color: #344047;
      font-size: 12px;
      line-height: 1.4;
    }
    .research-choice input { margin: 2px 0 0; accent-color: var(--accent); }
    .research-choice small { display: block; margin-top: 2px; color: var(--muted); }
    .research-candidates { display: grid; gap: 9px; }
    .research-candidate {
      display: grid;
      grid-template-columns: 20px minmax(0, 1fr) auto;
      gap: 9px;
      align-items: start;
      padding: 11px 0;
      border-bottom: 1px solid #edf0f2;
    }
    .research-candidate input { margin-top: 3px; accent-color: var(--accent); }
    .research-candidate strong { display: block; margin-bottom: 4px; font-size: 13px; }
    .research-candidate p { margin: 0; color: #445159; font-size: 12px; line-height: 1.55; }
    .research-candidate-meta { margin-top: 5px; color: var(--muted); font-size: 11px; }
    .research-candidate-action { min-width: 92px; }
    .background-task-bar {
      position: fixed;
      right: 20px;
      bottom: 20px;
      z-index: 90;
      width: min(390px, calc(100vw - 40px));
      padding: 12px;
      border: 1px solid #cad3d7;
      border-radius: 6px;
      background: #fff;
      box-shadow: 0 10px 30px rgba(24, 35, 40, .16);
    }
    .background-task-copy { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 9px; }
    .background-task-copy strong { font-size: 13px; }
    .background-task-copy span { color: var(--muted); font-size: 12px; }
    .background-task-controls { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: center; }
    .background-task-track { height: 5px; overflow: hidden; border-radius: 3px; background: #e7ecee; }
    .background-task-progress { width: 0; height: 100%; background: var(--accent); transition: width .2s ease; }
    .research-output { color: #273238; line-height: 1.7; overflow-wrap: anywhere; }
    .research-output h4 { margin: 18px 0 6px; font-size: 13px; color: var(--text); }
    .research-output h4:first-child { margin-top: 0; }
    .research-output p { margin: 0 0 8px; }
    .research-output ul { margin: 5px 0 12px; padding-left: 20px; }
    .research-output li { margin: 3px 0; }
    .research-paper-result { padding: 12px 0; border-bottom: 1px solid #edf0f2; }
    .research-status {
      display: inline-block;
      padding: 2px 6px;
      border-radius: 4px;
      background: #edf1f2;
      color: #46545b;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .research-status.continue { background: #e4f2e9; color: var(--success); }
    .research-status.adjust { background: #fff1dc; color: var(--warning); }
    .research-status.stop { background: #f8e5e5; color: var(--danger); }
    .research-status.implemented { background: #e4f2e9; color: var(--success); }
    .research-status.partial { background: #fff1dc; color: #8a5a00; }
    .research-status.missing { background: #f8e5e5; color: var(--danger); }
    .research-status.uncertain { background: #edf1f2; color: #56656d; }
    .correspondence-summary {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 1px;
      margin: 12px 0 16px;
      border: 1px solid var(--line);
      background: var(--line);
    }
    .correspondence-metric { padding: 10px; background: #fff; }
    .correspondence-metric strong { display: block; font-size: 17px; }
    .correspondence-metric span { color: var(--muted); font-size: 11px; }
    .correspondence-check { padding: 14px 0; border-bottom: 1px solid #edf0f2; }
    .correspondence-check:last-child { border-bottom: 0; }
    .correspondence-check-head { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; }
    .correspondence-check-head strong { flex: 1; font-size: 13px; }
    .code-location {
      margin: 7px 0;
      padding: 8px 10px;
      border-left: 3px solid #8a9aa2;
      background: #f5f7f8;
      color: #334148;
      font-family: Consolas, monospace;
      font-size: 11px;
      line-height: 1.5;
    }
    .research-prompt {
      width: 100%;
      min-height: 230px;
      resize: vertical;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      padding: 12px;
      background: #20282d;
      color: #eef2f3;
      font: 12px/1.6 Consolas, monospace;
    }
    .research-discovery-prompt {
      width: 100%;
      min-height: 190px;
      resize: vertical;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      padding: 11px 12px;
      background: #20282d;
      color: #eef2f3;
      font: 12px/1.65 Consolas, monospace;
    }
    .research-discovery-prompt::placeholder { color: #98a5ac; }
    .research-prompt-append { display: grid; gap: 7px; }
    .research-prompt-append .field { min-height: 72px; resize: vertical; }
    .research-inline { display: flex; flex-wrap: wrap; gap: 8px; align-items: end; }
    .research-inline .settings-field { flex: 1 1 220px; }
    .research-empty { color: var(--muted); font-size: 12px; line-height: 1.6; }
    .history-modal { width: min(900px, 100%); max-height: calc(100vh - 40px); display: grid; grid-template-rows: auto minmax(0, 1fr); }
    .history-body { overflow: auto; padding: 20px 24px 36px; }
    .history-question { margin: 0 0 18px; font-size: 17px; line-height: 1.5; }
    .history-answer { line-height: 1.75; overflow-wrap: anywhere; }
    .history-answer p { margin: 0 0 12px; }
    .history-answer .katex-display { overflow-x: auto; overflow-y: hidden; }
    .modal-head { display: flex; align-items: center; padding: 14px 16px; border-bottom: 1px solid var(--line); }
    .modal-head h2 { flex: 1; margin: 0; font-size: 16px; }
    .modal-head .icon-btn { color: var(--muted); }
    .modal-body { display: grid; gap: 10px; padding: 16px; }
    .modal-actions { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--line); }
    .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
    .file-picker {
      display: grid;
      place-items: center;
      min-height: 112px;
      padding: 16px;
      border: 1px dashed #aeb8bd;
      border-radius: 7px;
      background: var(--surface-alt);
      color: var(--muted);
      text-align: center;
      cursor: pointer;
    }
    .file-picker:hover { border-color: var(--accent); background: #f2f8f7; }
    .file-picker strong { display: block; margin-bottom: 5px; color: var(--text); }
    .file-picker input { display: none; }
    .import-pickers { display: grid; grid-template-columns: 1fr; gap: 8px; }
    .import-pickers.code-mode { grid-template-columns: 1fr 1fr; }
    .import-pickers.code-mode .file-picker { min-height: 100px; }
    .type-picker { display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px; padding: 3px; border-radius: 6px; background: #eef1f2; }
    .type-option { height: 34px; border: 0; border-radius: 4px; background: transparent; color: var(--muted); }
    .type-option.active { background: var(--surface); color: var(--text); box-shadow: 0 1px 2px rgba(25,35,40,.12); font-weight: 650; }
    .toast {
      position: fixed;
      z-index: 30;
      left: 50%;
      bottom: 18px;
      max-width: min(520px, calc(100vw - 30px));
      padding: 9px 13px;
      border-radius: 6px;
      background: #20282d;
      color: #fff;
      box-shadow: 0 6px 22px rgba(15,25,30,.24);
      opacity: 0;
      pointer-events: none;
      transform: translate(-50%, 8px);
      transition: .18s;
    }
    .toast.show { opacity: 1; transform: translate(-50%, 0); }
    .toast.error { background: #8e3535; }
    .mobile-only { display: none; }
    @media (max-width: 1120px) {
      .shell { grid-template-columns: 230px minmax(380px, 1fr) 280px; }
      .brand { width: 214px; }
    }
    @media (max-width: 900px) {
      .shell { grid-template-columns: 220px minmax(0, 1fr); }
      .brand { width: 204px; }
      .inspector {
        position: fixed;
        z-index: 12;
        top: var(--topbar);
        right: 0;
        bottom: 0;
        width: min(330px, 88vw);
        transform: translateX(100%);
        box-shadow: -10px 0 28px rgba(15,25,30,.14);
        transition: transform .2s;
      }
      .inspector.open { transform: translateX(0); }
      .mobile-only { display: inline-grid; }
      .research-body { grid-template-columns: 1fr; }
      .research-setup { max-height: 44vh; border-right: 0; border-bottom: 1px solid var(--line); }
    }
    @media (max-width: 680px) {
      .topbar { padding: 0 9px; }
      .brand { width: auto; }
      .brand span:last-child { display: none; }
      .connection { display: none; }
      .top-command { padding: 0 8px; }
      .shell { display: block; }
      .library {
        position: fixed;
        z-index: 13;
        top: var(--topbar);
        left: 0;
        bottom: 0;
        width: min(280px, 88vw);
        transform: translateX(-100%);
        box-shadow: 10px 0 28px rgba(15,25,30,.14);
        transition: transform .2s;
      }
      .library.open { transform: translateX(0); }
      .workspace { height: 100%; }
      .text-paper { padding: 28px 22px 60px; }
      .tool-bar { align-items: stretch; flex-wrap: wrap; }
      .tool-bar .field { flex-basis: 100%; }
      .output { padding: 15px 16px 60px; }
      .document-title-row { padding-left: 11px; padding-right: 9px; }
      .form-row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <button class="icon-btn mobile-only" id="libraryToggle" title="资料库">☰</button>
    <div class="brand"><span class="brand-mark">P</span><span>Papereading Master Beta</span></div>
    <div class="top-title" id="topTitle">论文阅读工作台</div>
    <div class="connection">本地运行</div>
    <nav class="workspace-switch">
      <button class="workspace-tab active" id="openReading">论文阅读</button>
      <button class="workspace-tab" id="openResearch">科研辅助</button>
    </nav>
    <button class="icon-btn" id="openSettings" title="API 设置">⚙</button>
    <button class="icon-btn mobile-only" id="inspectorToggle" title="阅读工具">▤</button>
  </header>

  <div class="shell" id="appShell">
    <aside class="library" id="library">
      <div class="side-head">
        <strong>资料库</strong>
        <button class="icon-btn" id="refreshDocs" title="刷新">↻</button>
        <button class="icon-btn" id="openImport" title="导入论文">＋</button>
      </div>
      <div class="library-search"><input class="field" id="fieldFilter" placeholder="搜索标题或研究领域"></div>
      <div class="library-controls">
        <select id="libraryView" aria-label="资料筛选">
          <option value="active">全部资料</option>
          <option value="pinned">已置顶</option>
          <option value="paper">论文</option>
          <option value="code">代码</option>
          <option value="archived">已归档</option>
        </select>
        <select id="categoryFilter" aria-label="分类筛选">
          <option value="">全部分类</option>
        </select>
      </div>
      <div class="doc-count" id="docCount">0 篇文档</div>
      <div class="doc-list" id="docList"></div>
    </aside>

    <main class="workspace">
      <div class="document-head">
        <div class="document-title-row">
          <div class="document-title">
            <h1 id="selectedTitle">尚未选择论文</h1>
            <p id="selectedMeta">从左侧资料库选择一篇论文</p>
          </div>
          <button class="icon-btn danger-icon" id="removeBtn" title="删除论文">×</button>
          <button class="icon-btn mobile-only" id="mobileInspector" title="阅读工具">▤</button>
        </div>
        <nav class="mode-tabs" id="modeTabs">
          <button class="mode-tab active" data-mode="source">原文</button>
          <button class="mode-tab" data-mode="analysis">智能阅读</button>
          <button class="mode-tab" data-mode="search">证据检索</button>
        </nav>
      </div>

      <div class="work-area">
        <section class="view source-view no-toolbar active" id="view-source">
          <div class="source-toolbar" id="sourceToolbar" hidden>
            <button class="icon-btn" id="previousPage" title="上一页">‹</button>
            <input class="page-jump" id="pageJump" type="number" min="1" value="1" aria-label="跳转页码">
            <span class="page-total" id="pageTotal">/ 0</span>
            <button class="icon-btn" id="nextPage" title="下一页">›</button>
          </div>
          <div class="empty" id="sourceEmpty"><div><strong>选择一篇论文开始阅读</strong><span>原文、阅读进度和笔记会在同一个工作台中打开</span></div></div>
          <div class="pdf-reader" id="pdfReader" hidden></div>
          <div class="text-paper" id="textPaper" hidden></div>
          <div class="markdown-workspace" id="markdownWorkspace" hidden>
            <div class="markdown-toolbar">
              <button class="btn" id="markdownEditMode">编辑</button>
              <button class="btn" id="markdownPreviewMode">预览</button>
              <span class="spacer"></span>
              <span class="save-state" id="markdownSaveState"></span>
              <button class="btn primary" id="saveMarkdown">保存</button>
            </div>
            <textarea class="markdown-editor" id="markdownEditor" spellcheck="false"></textarea>
            <div class="markdown-preview" id="markdownPreview" hidden></div>
          </div>
          <div class="code-workspace" id="codeWorkspace" hidden>
            <aside class="code-explorer">
              <div class="code-explorer-head" id="codeProjectTitle">Explorer</div>
              <div id="codeTree"></div>
            </aside>
            <section class="code-editor">
              <div class="code-tab">
                <span class="code-tab-title" id="codeTabTitle">未选择文件</span>
                <button class="code-tab-action" id="editCodeMarkdown" hidden>编辑 Markdown</button>
                <button class="code-tab-action" id="saveCodeMarkdown" hidden>保存</button>
              </div>
              <div class="code-content" id="codeContent"></div>
            </section>
          </div>
        </section>

        <section class="view tool-view" id="view-analysis">
          <div class="tool-bar">
            <button class="btn primary" id="readBtn">阅读全文</button>
            <button class="btn" id="regenerateAnalysis" hidden>重新生成</button>
            <div class="segmented" id="codeDetailMode" hidden>
              <button class="segment active" data-code-detail="brief">简略</button>
              <button class="segment" data-code-detail="detailed">详细</button>
            </div>
            <input class="field" id="compareTopic" placeholder="输入对比主题">
            <button class="btn" id="compareBtn">创新对比</button>
          </div>
          <div class="output" id="analysisOutput">
            <div class="empty"><div><strong>尚未生成阅读分析</strong><span>系统将按摘要、引言、方法、实验和结论逐节阅读</span></div></div>
          </div>
        </section>

        <section class="view tool-view" id="view-search">
          <div class="tool-bar">
            <input class="field" id="searchQuery" placeholder="检索当前论文中的证据">
            <button class="btn primary" id="searchBtn">检索</button>
          </div>
          <div class="output" id="searchResults">
            <div class="empty"><div><strong>检索论文证据</strong><span>结果会保留页码、章节和引用信息</span></div></div>
          </div>
        </section>

      </div>

      <section class="composer">
        <div class="messages" id="messages"></div>
        <div class="compose-row">
          <textarea class="field" id="chatQuestion" rows="1" placeholder="针对当前论文提问"></textarea>
          <button class="btn primary send-btn" id="chatBtn" title="发送">↑</button>
        </div>
      </section>
    </main>

    <aside class="inspector" id="inspector">
      <section class="inspector-section">
        <div class="section-label"><span>进度</span><span id="progressPercentLabel">0%</span></div>
        <div class="reading-progress-track"><div class="reading-progress-fill" id="progressFill"></div></div>
        <div class="reading-page-label" id="readingPageLabel">尚未开始阅读</div>
      </section>
      <nav class="inspector-tabs" id="inspectorTabs">
        <button class="inspector-tab active" data-inspector-panel="artifacts">图表</button>
        <button class="inspector-tab" data-inspector-panel="digest">阅读纪要</button>
      </nav>
      <section class="inspector-panel active" id="inspector-artifacts">
        <div class="inspector-section artifact-section">
          <div class="section-label">
            <span>图表、公式与算法</span>
            <span><button class="icon-btn" id="refreshArtifacts" title="重新识别图表">↻</button><span id="artifactCount">0</span></span>
          </div>
          <div class="artifact-list" id="artifactList"><div class="muted">选择论文后显示图表</div></div>
        </div>
      </section>
      <section class="inspector-panel" id="inspector-digest">
        <div class="inspector-section">
          <div class="digest-actions">
            <button class="btn" id="addTimelineNote">添加笔记</button>
            <button class="btn" id="summarizeTimeline">一键总结</button>
          </div>
          <div class="note-composer" id="timelineNoteComposer" hidden>
            <textarea id="timelineNoteText" placeholder="使用 Markdown 记录当前想法..."></textarea>
            <div class="note-composer-actions">
              <button class="btn" id="cancelTimelineNote">取消</button>
              <button class="btn primary" id="saveTimelineNote">添加</button>
            </div>
          </div>
          <div class="section-label"><span>阅读时间线</span></div>
          <div class="digest-list" id="readingDigestText"></div>
          <div class="digest-empty" id="readingDigestEmpty">笔记、问答和生成记录会按时间出现在这里。</div>
        </div>
      </section>
    </aside>
  </div>

  <div class="modal-backdrop" id="importModal">
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="importTitle">
      <div class="modal-head"><h2 id="importTitle">添加本地资料</h2><button class="icon-btn" id="closeImport" title="关闭">×</button></div>
      <div class="modal-body">
        <div class="type-picker" id="typePicker">
          <button class="type-option active" type="button" data-type="paper">论文</button>
          <button class="type-option" type="button" data-type="code">代码</button>
        </div>
        <div class="import-pickers" id="importPickers">
          <label class="file-picker" for="ingestFile">
            <span><strong id="filePickerTitle">点击选择文件</strong><span id="filePickerHint">支持 PDF、Markdown、Notebook 和常见代码文件</span></span>
            <input id="ingestFile" type="file" multiple accept=".pdf,.txt,.md,.markdown,.rst">
          </label>
          <label class="file-picker" id="folderPicker" for="ingestFolder" hidden>
            <span><strong id="folderPickerTitle">选择代码文件夹</strong><span id="folderPickerHint">保留目录结构，只导入支持的文本代码文件</span></span>
            <input id="ingestFolder" type="file" webkitdirectory multiple>
          </label>
        </div>
      </div>
      <div class="modal-actions"><button class="btn" id="cancelImport">取消</button><button class="btn primary" id="ingestBtn">导入</button></div>
    </div>
  </div>
  <div class="modal-backdrop" id="categoryModal">
    <div class="modal compact-modal" role="dialog" aria-modal="true" aria-labelledby="categoryTitle">
      <div class="modal-head"><h2 id="categoryTitle">设置分类</h2><button class="icon-btn" id="closeCategory" title="关闭">×</button></div>
      <div class="modal-body">
        <label class="settings-field">分类名称
          <input class="field" id="categoryName" list="categorySuggestions" maxlength="60" placeholder="例如：推理加速、待读、课程资料">
        </label>
        <datalist id="categorySuggestions"></datalist>
        <div class="settings-note">留空保存可移出当前分类，不会删除资料。</div>
      </div>
      <div class="modal-actions"><button class="btn" id="cancelCategory">取消</button><button class="btn primary" id="saveCategory">保存分类</button></div>
    </div>
  </div>
  <div class="modal-backdrop" id="historyModal">
    <div class="modal history-modal" role="dialog" aria-modal="true" aria-labelledby="historyTitle">
      <div class="modal-head"><h2 id="historyTitle">完整阅读记录</h2><button class="icon-btn" id="closeHistory" title="关闭">×</button></div>
      <div class="history-body">
        <h3 class="history-question" id="historyQuestion"></h3>
        <div class="history-answer message-content" id="historyAnswer"></div>
      </div>
    </div>
  </div>
  <div class="modal-backdrop" id="researchTaskModal">
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="researchTaskModalTitle">
      <div class="modal-head"><h2 id="researchTaskModalTitle">新建科研任务</h2><button class="icon-btn" id="closeResearchTaskModal" title="关闭">×</button></div>
      <div class="modal-body">
        <label class="settings-field">任务名称
          <input class="field" id="newResearchTaskName" maxlength="100" placeholder="例如：动态 Gamma 的最小可行实验">
        </label>
      </div>
      <div class="modal-actions"><button class="btn" id="cancelResearchTask">取消</button><button class="btn primary" id="confirmResearchTask">创建任务</button></div>
    </div>
  </div>
  <section class="research-workspace" id="researchWorkspace" hidden>
      <div class="research-page-head">
        <h1 id="researchTitle">科研辅助</h1>
        <p>从论文理解到可执行实验，再根据结果继续、调整或中止</p>
      </div>
      <div class="research-body">
        <aside class="research-setup">
          <div class="research-form">
            <div class="research-inline">
              <label class="settings-field">最近任务
                <select class="field" id="researchTaskSelect">
                  <option value="">选择任务</option>
                </select>
              </label>
              <button class="btn" id="newResearchTask">新建</button>
            </div>
            <label class="settings-field">任务名称
              <input class="field" id="researchTaskName" maxlength="100" placeholder="任务名称">
            </label>
            <label class="settings-field">论文发现 Prompt
              <textarea class="research-discovery-prompt" id="researchDirection" placeholder="研究主题：
希望解决的问题：
重点关注：
排除范围：
期望论文类型或时间范围："></textarea>
            </label>
            <div>
              <div class="section-label"><span>本地论文</span></div>
              <div class="research-choice-list" id="researchPaperChoices"></div>
            </div>
            <div>
              <div class="section-label"><span>本地代码项目</span></div>
              <div class="research-choice-list" id="researchCodeChoices"></div>
            </div>
            <button class="btn primary" id="researchDiscover">按当前 Prompt 寻找</button>
            <div class="research-prompt-append">
              <textarea class="field" id="researchPromptAppend" rows="3" placeholder="追加要求，例如：更关注动态草稿长度，不要安全对齐方向"></textarea>
              <button class="btn" id="researchAppendDiscover">追加并重新寻找</button>
            </div>
            <div class="settings-note">外部论文当前基于 arXiv 元数据与摘要发现；只有本地论文会按全文证据分析。</div>
          </div>
        </aside>
        <main class="research-results">
          <section class="research-section">
            <div class="research-section-head">
              <h3>1. 候选相关论文</h3>
              <div class="research-inline">
                <label class="settings-field">排序
                  <select class="field" id="researchCandidateSort">
                    <option value="relevance">相关度</option>
                    <option value="newest">时间：最新优先</option>
                    <option value="oldest">时间：最早优先</option>
                  </select>
                </label>
                <button class="btn primary" id="researchAnalyze" disabled>综合分析所选论文</button>
              </div>
            </div>
            <div class="research-candidates" id="researchCandidateList">
              <div class="research-empty">输入方向或选择本地论文后开始发现。也可以不选外部论文，只分析本地材料。</div>
            </div>
          </section>
          <section class="research-section">
            <div class="research-section-head"><h3>2. 创新、相关性与不足</h3></div>
            <div class="research-output" id="researchAnalysisOutput">
              <div class="research-empty">完成论文选择后，这里会给出跨论文综合、代码对应关系和可验证的后续方向。</div>
            </div>
          </section>
          <section class="research-section">
            <div class="research-section-head">
              <h3>3. 论文与代码对应检查</h3>
              <button class="btn primary" id="researchCorrespondence" disabled>开始检查</button>
            </div>
            <div class="research-output" id="researchCorrespondenceOutput">
              <div class="research-empty">选择至少一篇本地论文和一个代码项目后，检查算法、公式、数据处理、参数、指标与实验配置的实现情况。</div>
            </div>
          </section>
          <section class="research-section">
            <div class="research-section-head"><h3>4. 复现或最小可行实验</h3></div>
            <div class="research-form">
              <div class="research-inline">
                <label class="settings-field">实验类型
                  <select class="field" id="researchExperimentMode">
                    <option value="mvp">最小可行实验</option>
                    <option value="reproduction">论文复现</option>
                  </select>
                </label>
                <label class="settings-field">后续方向
                  <select class="field" id="researchDirectionIndex">
                    <option value="">由 Agent 判断</option>
                  </select>
                </label>
              </div>
              <label class="settings-field">额外目标或约束
                <textarea class="field" id="researchObjective" rows="3" placeholder="例如：仅使用单卡 24GB 显存，先在小数据集验证"></textarea>
              </label>
              <button class="btn primary" id="researchPlan" disabled>生成实验方案与 Codex Prompt</button>
              <div class="research-output" id="researchExperimentOutput"></div>
              <div id="researchPromptArea" hidden>
                <div class="research-section-head">
                  <h3>交给 Codex 的 Prompt</h3>
                  <button class="btn" id="copyResearchPrompt">复制</button>
                </div>
                <textarea class="research-prompt" id="researchPrompt" readonly></textarea>
              </div>
            </div>
          </section>
          <section class="research-section">
            <div class="research-section-head"><h3>5. 根据实验结果继续、调整或中止</h3></div>
            <div class="research-form">
              <label class="settings-field">实验结果
                <textarea class="field" id="researchResult" rows="5" placeholder="粘贴指标、日志摘要、失败原因或观察结果"></textarea>
              </label>
              <label class="research-attachment-picker" for="researchResultFiles">
                <span><strong>添加实验结果附件</strong><br>支持 Markdown、PNG、JPEG、WebP；也可以直接在上方粘贴截图</span>
                <input id="researchResultFiles" type="file" multiple accept=".md,.markdown,image/png,image/jpeg,image/webp">
              </label>
              <div class="research-attachments" id="researchAttachmentList"></div>
              <button class="btn primary" id="researchAssess" disabled>评估下一步</button>
              <div class="research-output" id="researchAssessmentOutput"></div>
            </div>
          </section>
        </main>
      </div>
  </section>
  <div class="modal-backdrop" id="settingsModal">
    <div class="modal settings-modal" role="dialog" aria-modal="true" aria-labelledby="settingsTitle">
      <div class="modal-head"><h2 id="settingsTitle">模型 API 设置</h2><button class="icon-btn" id="closeSettings" title="关闭">×</button></div>
      <div class="modal-body">
        <section class="settings-group">
          <h3>界面与回答语言</h3>
          <label class="settings-field">全局语言
            <select class="field" id="appLanguage">
              <option value="zh">中文</option>
              <option value="en">English</option>
            </select>
          </label>
          <div class="settings-note">界面、文字模型和视觉模型会统一使用所选语言。</div>
        </section>
        <section class="settings-group">
          <h3>文字理解模型</h3>
          <label class="settings-field">服务类型
            <select class="field" id="textProvider">
              <option value="custom">OpenAI 兼容 / Qwen</option>
              <option value="openai">OpenAI</option>
              <option value="deepseek">DeepSeek</option>
              <option value="local">本地服务</option>
            </select>
          </label>
          <label class="settings-field">模型名称<input class="field" id="textModel" placeholder="例如 qwen-plus"></label>
          <label class="settings-field">Base URL<input class="field" id="textBaseUrl" placeholder="例如 https://dashscope.aliyuncs.com/compatible-mode/v1"></label>
          <label class="settings-field">API Key<input class="field" id="textApiKey" type="password" autocomplete="off" placeholder="API Key"></label>
        </section>
        <section class="settings-group">
          <h3>视觉理解模型</h3>
          <label class="settings-field">服务状态
            <select class="field" id="visionProvider">
              <option value="disabled">不启用</option>
              <option value="openai_compatible">OpenAI 兼容视觉接口</option>
            </select>
          </label>
          <label class="settings-field">模型名称<input class="field" id="visionModel" placeholder="例如 qwen-vl-max"></label>
          <label class="settings-field">Base URL<input class="field" id="visionBaseUrl" placeholder="视觉模型兼容接口地址"></label>
          <label class="settings-field">API Key<input class="field" id="visionApiKey" type="password" autocomplete="off" placeholder="视觉模型 API Key"></label>
        </section>
        <div class="settings-note" id="settingsStatus">配置会写入本机项目的 .env，并立即用于后续文字问答和图表解释。</div>
      </div>
      <div class="modal-actions"><button class="btn" id="cancelSettings">取消</button><button class="btn primary" id="saveSettings">保存设置</button></div>
    </div>
  </div>
  <div class="floating-layer" id="floatingLayer"></div>
  <div class="background-task-bar" id="backgroundTaskBar" hidden>
    <div class="background-task-copy">
      <strong id="backgroundTaskTitle">正在执行</strong>
      <span id="backgroundTaskStatus">准备中</span>
    </div>
    <div class="background-task-controls">
      <div class="background-task-track"><div class="background-task-progress" id="backgroundTaskProgress"></div></div>
      <button class="btn" id="cancelBackgroundTask">取消</button>
    </div>
  </div>
  <div class="toast" id="toast"></div>

  <script>
    const state = {
      docs: [],
      selected: null,
      workspace: 'reading',
      mode: 'source',
      ingestType: 'paper',
      reading: null,
      currentPage: 0,
      pageCount: 0,
      progressSaveTimer: null,
      messages: [],
      artifacts: [],
      windowIndex: 0,
      activeArtifactWindow: null,
      activeArtifactAbort: null,
      activeArtifactCleanup: null,
      docMenuId: null,
      categoryTargetId: null,
      readingHistory: [],
      draggedTimelineId: null,
      codeFiles: [],
      activeCodeId: null,
      codeFileCache: new Map(),
      codeLoadToken: 0,
      codeMarkdownEditing: false,
      codeDetail: 'brief',
      markdownDirty: false,
      language: 'zh',
      lastPdfCopyAt: 0,
      lastPdfCopyText: '',
      researchTasks: [],
      researchTask: null,
      researchCandidates: [],
      researchAnalysis: null,
      researchCorrespondence: null,
      researchExperiment: null,
      researchAttachments: [],
      researchSaveTimer: null,
      activeLongTask: null
    };
    const $ = id => document.getElementById(id);
    const t = (zh, en) => state.language === 'en' ? en : zh;
    const UI_TRANSLATIONS = new Map(Object.entries({
      '论文阅读工作台': 'Paper Reading Workspace',
      '本地运行': 'Local',
      '资料库': 'Library',
      '全部资料': 'All Materials',
      '已置顶': 'Pinned',
      '论文': 'Papers',
      '代码': 'Code',
      '已归档': 'Archived',
      '全部分类': 'All Categories',
      '未分类': 'Uncategorized',
      '尚未选择论文': 'No Paper Selected',
      '从左侧资料库选择一篇论文': 'Select a paper from the library',
      '原文': 'Source',
      '智能阅读': 'Smart Reading',
      '证据检索': 'Evidence Search',
      '选择一篇论文开始阅读': 'Select a paper to start reading',
      '原文、阅读进度和笔记会在同一个工作台中打开': 'The source, reading progress, and notes open in one workspace',
      '编辑': 'Edit',
      '预览': 'Preview',
      '保存': 'Save',
      '未选择文件': 'No File Selected',
      '编辑 Markdown': 'Edit Markdown',
      '阅读全文': 'Read Full Paper',
      '创新对比': 'Compare Contributions',
      '尚未生成阅读分析': 'No Reading Analysis Yet',
      '系统将按摘要、引言、方法、实验和结论逐节阅读': 'The paper will be read section by section',
      '检索': 'Search',
      '检索论文证据': 'Search Paper Evidence',
      '结果会保留页码、章节和引用信息': 'Results retain pages, sections, and citations',
      '进度': 'Progress',
      '尚未开始阅读': 'Not Started',
      '图表': 'Artifacts',
      '阅读纪要': 'Reading Digest',
      '图表、公式与算法': 'Figures, Equations, and Algorithms',
      '重新识别图表': 'Rebuild Artifact List',
      '选择论文后显示图表': 'Artifacts appear after selecting a paper',
      '我的笔记': 'My Notes',
      '向论文提问后，这里会保留简短的回忆提示。': 'Short recall cues appear here after asking questions.',
      '导入资料': 'Import Material',
      '添加本地资料': 'Add Local Material',
      '资料类型': 'Material Type',
      '论文 PDF、Markdown 与文本': 'Paper PDF, Markdown, and text',
      '代码文件或项目目录': 'Code files or project folder',
      '选择文件': 'Choose Files',
      '点击选择文件': 'Click to Choose Files',
      '支持 PDF、Markdown、Notebook 和常见代码文件': 'Supports PDF, Markdown, notebooks, and common code files',
      '选择代码文件夹': 'Choose Code Folder',
      '保留目录结构，只导入支持的文本代码文件': 'Preserves folders and imports supported text code files only',
      '取消': 'Cancel',
      '开始导入': 'Import',
      '导入': 'Import',
      '设置分类': 'Set Category',
      '分类名称': 'Category Name',
      '留空保存可移出当前分类，不会删除资料。': 'Leave blank to remove the category without deleting the material.',
      '保存分类': 'Save Category',
      '完整阅读记录': 'Full Reading Record',
      '模型 API 设置': 'Model API Settings',
      '界面与回答语言': 'Interface and Response Language',
      '全局语言': 'Global Language',
      '界面、文字模型和视觉模型会统一使用所选语言。': 'The interface, text model, and vision model use the selected language.',
      '文字理解模型': 'Text Model',
      '视觉理解模型': 'Vision Model',
      '服务类型': 'Provider',
      '服务状态': 'Status',
      '模型名称': 'Model Name',
      '本地服务': 'Local Service',
      '不启用': 'Disabled',
      'OpenAI 兼容视觉接口': 'OpenAI-compatible Vision API',
      '配置会写入本机项目的 .env，并立即用于后续文字问答和图表解释。': 'Settings are stored locally and apply immediately to subsequent model calls.',
      '保存设置': 'Save Settings',
      '刷新': 'Refresh',
      '正在执行': 'Running',
      '准备中': 'Preparing',
      '关闭': 'Close',
      '删除论文': 'Delete Material',
      '阅读工具': 'Reading Tools',
      'API 设置': 'API Settings',
      '置顶': 'Pin',
      '取消置顶': 'Unpin',
      '归档': 'Archive',
      '取消归档': 'Unarchive',
      '删除': 'Delete',
      '代码解析': 'Code Analysis',
      '解析项目': 'Analyze Project',
      '当前论文没有识别到图表': 'No artifacts were detected in this paper',
      '正在解释图表...': 'Analyzing artifact...',
      '添加到纪要': 'Add to Digest',
      '已添加到纪要': 'Added to Digest',
      '保存裁剪': 'Save Crop',
      '拖动图像调整位置，拖动边角扩大或缩小当前范围。': 'Drag the image to reposition it, or drag the handles to resize the crop.',
      '该资料没有可裁剪的 PDF 图像。': 'This material has no croppable PDF image.',
      '没有生成解释。': 'No explanation was generated.',
      '搜索标题或研究领域': 'Search title or field',
      '输入对比主题': 'Enter a comparison topic',
      '检索当前论文中的证据': 'Search evidence in the current paper',
      '针对当前论文提问': 'Ask about the current paper',
      '针对当前代码项目提问': 'Ask about the current code project',
      '使用 Markdown 记录自己的想法...': 'Write your own notes in Markdown...',
      '分类名称，可留空': 'Category name, optional',
      '例如：推理加速、待读、课程资料': 'For example: inference, reading list, course materials',
      '科研辅助': 'Research Copilot',
      '论文阅读': 'Paper Reading',
      '科研辅助工作台': 'Research Copilot Workspace',
      '最近任务': 'Recent Tasks',
      '新任务': 'New Task',
      '新建': 'New',
      '研究方向或目标': 'Research Direction or Goal',
      '论文发现 Prompt': 'Paper Discovery Prompt',
      '按当前 Prompt 寻找': 'Search with Current Prompt',
      '追加并重新寻找': 'Append and Search Again',
      '本地论文': 'Local Papers',
      '本地代码项目': 'Local Code Projects',
      '寻找相关论文': 'Find Related Papers',
      '外部论文当前基于 arXiv 元数据与摘要发现；只有本地论文会按全文证据分析。': 'External papers are discovered from arXiv metadata and abstracts; only local papers are analyzed as full text.',
      '1. 候选相关论文': '1. Related Paper Candidates',
      '综合分析所选论文': 'Analyze Selected Papers',
      '2. 创新、相关性与不足': '2. Innovation, Relevance, and Limitations',
      '3. 复现或最小可行实验': '3. Reproduction or MVP Experiment',
      '实验类型': 'Experiment Type',
      '最小可行实验': 'MVP Experiment',
      '论文复现': 'Paper Reproduction',
      '后续方向': 'Future Direction',
      '由 Agent 判断': 'Let Agent Decide',
      '额外目标或约束': 'Additional Goals or Constraints',
      '生成实验方案与 Codex Prompt': 'Generate Experiment Plan and Codex Prompt',
      '交给 Codex 的 Prompt': 'Prompt for Codex',
      '复制': 'Copy',
      '4. 根据实验结果继续、调整或中止': '4. Continue, Adjust, or Stop from Results',
      '实验结果': 'Experiment Results',
      '评估下一步': 'Evaluate Next Step',
      '输入方向或选择本地论文后开始发现。也可以不选外部论文，只分析本地材料。': 'Enter a direction or select local papers. External candidates are optional.',
      '完成论文选择后，这里会给出跨论文综合、代码对应关系和可验证的后续方向。': 'After selection, this section compares papers, maps code, and proposes testable directions.',
      '论文与代码对应检查': 'Paper-Code Correspondence Check',
      '开始检查': 'Run Check',
      '资料库中还没有论文。': 'No papers in the library.',
      '资料库中还没有代码项目。': 'No code projects in the library.',
      '尚未发现外部论文。已有本地论文时，仍可直接进行综合分析。': 'No external papers found. Local papers can still be analyzed directly.',
      '例如：降低 RAG 重排序的推理延迟，同时尽量保持召回率': 'Example: reduce RAG reranking latency while preserving recall',
      '例如：仅使用单卡 24GB 显存，先在小数据集验证': 'Example: use one 24GB GPU and validate on a small dataset first',
      '粘贴指标、日志摘要、失败原因或观察结果': 'Paste metrics, log summaries, failures, or observations'
      ,'添加实验结果附件': 'Add Experiment Result Attachments'
      ,'支持 Markdown、PNG、JPEG、WebP；也可以直接在上方粘贴截图': 'Supports Markdown, PNG, JPEG, and WebP; screenshots can also be pasted above'
      ,'视觉模型已解析': 'Analyzed by Vision Model'
      ,'尚未配置视觉模型': 'Vision Model Not Configured'
      ,'视觉解析失败': 'Vision Analysis Failed'
      ,'Markdown 已读取': 'Markdown Loaded'
      ,'拖动排序': 'Drag to Reorder'
      ,'删除记录': 'Delete Record'
      ,'确定删除这条阅读记录？': 'Delete this reading record?'
      ,'任务名称': 'Task Name'
      ,'选择任务': 'Select Task'
      ,'新建科研任务': 'New Research Task'
      ,'创建任务': 'Create Task'
      ,'排序': 'Sort'
      ,'相关度': 'Relevance'
      ,'时间：最新优先': 'Date: Newest First'
      ,'时间：最早优先': 'Date: Oldest First'
      ,'追加要求，例如：更关注动态草稿长度，不要安全对齐方向': 'Additional requirement, e.g. focus on dynamic draft length and exclude safety alignment'
    }));
    [
      ['重新生成', 'Regenerate'],
      ['简略', 'Brief'],
      ['详细', 'Detailed'],
      ['添加笔记', 'Add Note'],
      ['一键总结', 'Summarize'],
      ['阅读时间线', 'Reading Timeline'],
      ['笔记', 'Note'],
      ['问答', 'Q&A'],
      ['图表解释', 'Artifact Explanation'],
      ['总结', 'Summary'],
      ['记录', 'Record'],
      ['条结果', 'results'],
      ['添加中...', 'Adding...'],
      ['总结中...', 'Summarizing...']
    ].forEach(([zh, en]) => UI_TRANSLATIONS.set(zh, en));
    const UI_TRANSLATIONS_REVERSE = new Map([...UI_TRANSLATIONS].map(([zh, en]) => [en, zh]));
    const excludedTranslationNode = node => node.parentElement?.closest(
      '.message-content,.stream-report,.artifact-explanation,.markdown-preview,.markdown-editor,' +
      '.code-content,.pdf-reader,.text-paper,.history-answer,.history-question,.pdf-translation'
    );
    const translateUiText = value => {
      const source = String(value || '');
      const trimmed = source.trim();
      if (!trimmed) return source;
      const map = state.language === 'en' ? UI_TRANSLATIONS : UI_TRANSLATIONS_REVERSE;
      let translated = map.get(trimmed);
      if (!translated && state.language === 'en') {
        translated = trimmed
          .replace(/^(\d+) 篇文档$/, '$1 documents')
          .replace(/^(\d+) 项 · 共 (\d+) 项$/, '$1 items · $2 total')
          .replace(/^第 (\d+) 页$/, 'Page $1')
          .replace(/^第 (\d+) 页 · /, 'Page $1 · ');
      } else if (!translated && state.language === 'zh') {
        translated = trimmed
          .replace(/^(\d+) documents$/, '$1 篇文档')
          .replace(/^(\d+) items · (\d+) total$/, '$1 项 · 共 $2 项')
          .replace(/^Page (\d+)$/, '第 $1 页')
          .replace(/^Page (\d+) · /, '第 $1 页 · ');
      }
      if (!translated || translated === trimmed) return source;
      return source.replace(trimmed, translated);
    };
    const localizeUi = (root=document.body) => {
      document.documentElement.lang = state.language === 'en' ? 'en' : 'zh-CN';
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach(node => {
        if (!excludedTranslationNode(node)) node.nodeValue = translateUiText(node.nodeValue);
      });
      const attributeMap = state.language === 'en' ? UI_TRANSLATIONS : UI_TRANSLATIONS_REVERSE;
      root.querySelectorAll?.('[title],[placeholder],[aria-label]').forEach(node => {
        ['title', 'placeholder', 'aria-label'].forEach(attribute => {
          const value = node.getAttribute(attribute);
          if (value && attributeMap.has(value)) node.setAttribute(attribute, attributeMap.get(value));
        });
      });
    };
    let localizationQueued = false;
    const localizationRoots = new Set();
    const queueLocalization = records => {
      (records || []).forEach(record => localizationRoots.add(record.target));
      if (localizationQueued) return;
      localizationQueued = true;
      requestAnimationFrame(() => {
        localizationQueued = false;
        const roots = [...localizationRoots];
        localizationRoots.clear();
        roots.forEach(root => localizeUi(root instanceof Element ? root : root.parentElement || document.body));
      });
    };
    new MutationObserver(queueLocalization).observe(document.body, {childList: true, subtree: true});
    const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
    const tokenizeMath = value => {
      const tokens = [];
      const text = String(value ?? '').replace(
        /\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$(?!\$)(?:\\.|[^$\n])+\$/g,
        match => {
          const token = `@@MATH_${tokens.length}@@`;
          tokens.push(escapeHtml(match));
          return token;
        }
      );
      return {
        text,
        restore: html => html.replace(/@@MATH_(\d+)@@/g, (_match, index) => tokens[Number(index)] || '')
      };
    };
    const api = async (path, payload) => {
      const response = await fetch(path, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload || {})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '请求失败');
      return data;
    };
    const get = async path => {
      const response = await fetch(path);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '请求失败');
      return data;
    };
    let toastTimer;
    const notify = (message, error=false) => {
      const toast = $('toast');
      toast.textContent = message;
      toast.className = 'toast show' + (error ? ' error' : '');
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => toast.className = 'toast', 2600);
    };
    const withBusy = async (button, label, action) => {
      const original = button.textContent;
      button.disabled = true;
      button.textContent = label;
      try { return await action(); }
      finally { button.disabled = false; button.textContent = original; }
    };
    const showLongTask = (title, status='准备中', progress=0) => {
      $('backgroundTaskTitle').textContent = title;
      $('backgroundTaskStatus').textContent = status;
      $('backgroundTaskProgress').style.width = `${Math.max(0, Math.min(Number(progress) || 0, 100))}%`;
      $('backgroundTaskBar').hidden = false;
    };
    const hideLongTask = task => {
      if (task && state.activeLongTask !== task) return;
      state.activeLongTask = null;
      $('backgroundTaskBar').hidden = true;
      $('backgroundTaskProgress').style.width = '0%';
    };
    const runBackgroundTask = async (kind, payload, title) => {
      if (state.activeLongTask) throw new Error(t('已有长任务正在执行', 'Another long task is running'));
      const started = await api('/api/background/start', {kind, payload});
      const active = {type: 'background', id: started.task.id};
      state.activeLongTask = active;
      showLongTask(title, started.task.message, started.task.progress);
      try {
        while (true) {
          await new Promise(resolve => setTimeout(resolve, 500));
          const data = await get(`/api/background-task?id=${encodeURIComponent(active.id)}`);
          const task = data.task;
          showLongTask(title, task.message || task.status, task.progress);
          if (task.status === 'completed') return task.result;
          if (task.status === 'cancelled') throw new DOMException('已取消', 'AbortError');
          if (task.status === 'failed') throw new Error(task.error || t('后台任务失败', 'Background task failed'));
        }
      } finally {
        hideLongTask(active);
      }
    };
    const requireDoc = () => {
      if (!state.selected) throw new Error('请先选择一篇论文');
      return {
        document_id: state.selected.id,
        title: state.selected.title,
        field: state.selected.field
      };
    };
    const typeLabel = type => ({
      paper: t('论文', 'Paper'), document: t('文档', 'Document'), code: t('代码', 'Code'),
      related_work: t('文档', 'Document'), supplement: t('文档', 'Document'), note: t('文档', 'Document')
    }[type] || type || t('文档', 'Document'));
    const normalizedType = type => (
      type === 'paper' || type === 'code' ? type : 'document'
    );
    const roleLabel = value => ({
      abstract: t('摘要', 'Abstract'), introduction: t('引言', 'Introduction'),
      problem: t('研究问题', 'Research Problem'), method: t('方法', 'Method'),
      evidence: t('实验与证据', 'Experiments and Evidence'), experiment: t('实验', 'Experiments'),
      results: t('结果', 'Results'), limitation: t('局限性', 'Limitations'),
      conclusion: t('结论', 'Conclusion'), related_work: t('相关工作', 'Related Work')
    }[value] || value || t('章节', 'Section'));
    const artifactLabel = artifact => {
      const text = artifact.caption || artifact.text || '';
      const number = artifact.metadata?.number
        || text.match(/(?:Figure|Fig\.?|Table|Algorithm|Equation)\s*(\d+)/i)?.[1]
        || text.match(/(?:图|表|公式|算法)\s*(\d+)/)?.[1]
        || '?';
      return ({
        figure: `${t('图', 'Figure')} ${number}`,
        table: `${t('表', 'Table')} ${number}`,
        formula: `${t('公式', 'Equation')} ${number}`,
        algorithm: `Algorithm ${number}`
      }[artifact.kind] || `${artifact.kind} ${number}`);
    };

    const loadDocs = async () => {
      const data = await get('/api/documents');
      state.docs = data.documents || [];
      if (state.selected) {
        state.selected = state.docs.find(doc => doc.id === state.selected.id) || null;
      }
      renderCategoryOptions();
      renderDocs();
      renderSelected();
    };
    const renderCategoryOptions = () => {
      const current = $('categoryFilter').value;
      const categories = [...new Set(state.docs.map(doc => doc.category).filter(Boolean))]
        .sort((left, right) => left.localeCompare(right, 'zh-CN'));
      $('categoryFilter').innerHTML = '<option value="">全部分类</option>' + categories.map(category =>
        `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`
      ).join('');
      $('categoryFilter').value = categories.includes(current) ? current : '';
      $('categorySuggestions').innerHTML = categories.map(category =>
        `<option value="${escapeHtml(category)}"></option>`
      ).join('');
    };
    const visibleDocuments = () => {
      const query = $('fieldFilter').value.trim().toLocaleLowerCase();
      const view = $('libraryView').value;
      const category = $('categoryFilter').value;
      return state.docs.filter(doc => {
        if (query && !`${doc.title} ${doc.field || ''} ${doc.category || ''}`.toLocaleLowerCase().includes(query)) return false;
        if (category && doc.category !== category) return false;
        if (view === 'archived') return Boolean(doc.archived);
        if (doc.archived) return false;
        if (view === 'pinned') return Boolean(doc.pinned);
        if (['paper', 'document', 'code'].includes(view)) return normalizedType(doc.document_type) === view;
        return true;
      }).sort((left, right) =>
        Number(Boolean(right.pinned)) - Number(Boolean(left.pinned))
        || String(left.category || '').localeCompare(String(right.category || ''), 'zh-CN')
        || String(left.title || '').localeCompare(String(right.title || ''), 'zh-CN')
      );
    };
    const renderDocs = () => {
      const documents = visibleDocuments();
      const activeTotal = state.docs.filter(doc => !doc.archived).length;
      $('docCount').textContent = `${documents.length} 项 · 共 ${activeTotal} 项`;
      const groups = new Map();
      documents.forEach(doc => {
        const group = doc.category || '未分类';
        if (!groups.has(group)) groups.set(group, []);
        groups.get(group).push(doc);
      });
      $('docList').innerHTML = [...groups.entries()].map(([group, items]) => `
        <div class="doc-group-label">${escapeHtml(group)}</div>
        ${items.map(doc => `
          <div class="doc-entry" data-entry-id="${escapeHtml(doc.id)}">
            <button class="doc ${state.selected?.id === doc.id ? 'active' : ''}" data-id="${escapeHtml(doc.id)}">
              <span class="doc-title">${escapeHtml(doc.title)}</span>
              <span class="doc-meta">
                <span class="doc-flags">
                  ${doc.pinned ? '<span class="doc-flag">置顶</span>' : ''}
                  ${doc.archived ? '<span class="doc-flag archived">归档</span>' : ''}
                </span>
                ${escapeHtml(doc.field || '未分类')} · ${escapeHtml(typeLabel(doc.document_type))}
              </span>
            </button>
            <button class="doc-more ${state.docMenuId === doc.id ? 'active' : ''}" data-menu-id="${escapeHtml(doc.id)}" title="资料操作">⋯</button>
            <div class="doc-menu" data-doc-menu="${escapeHtml(doc.id)}" ${state.docMenuId === doc.id ? '' : 'hidden'}>
              <button data-doc-action="pin" data-id="${escapeHtml(doc.id)}">${doc.pinned ? '取消置顶' : '置顶'}</button>
              <button data-doc-action="category" data-id="${escapeHtml(doc.id)}">设置分类</button>
              <button data-doc-action="archive" data-id="${escapeHtml(doc.id)}">${doc.archived ? '恢复资料' : '归档'}</button>
              <button class="danger" data-doc-action="delete" data-id="${escapeHtml(doc.id)}">删除</button>
            </div>
          </div>
        `).join('')}
      `).join('') || '<div class="empty"><div><strong>没有符合条件的资料</strong><span>调整筛选条件或导入新资料</span></div></div>';
      document.querySelectorAll('.doc').forEach(button => {
        button.onclick = () => selectDocument(button.dataset.id);
      });
      document.querySelectorAll('.doc-more').forEach(button => {
        button.onclick = event => {
          event.stopPropagation();
          state.docMenuId = state.docMenuId === button.dataset.menuId ? null : button.dataset.menuId;
          renderDocs();
        };
      });
      document.querySelectorAll('[data-doc-action]').forEach(button => {
        button.onclick = event => {
          event.stopPropagation();
          handleDocumentAction(button.dataset.docAction, button.dataset.id);
        };
      });
    };
    const updateDocumentOrganization = async (documentId, changes, message) => {
      const data = await api('/api/document-organize', {document_id: documentId, ...changes});
      state.docs = state.docs.map(doc => doc.id === documentId ? data.document : doc);
      if (state.selected?.id === documentId) state.selected = data.document;
      state.docMenuId = null;
      renderCategoryOptions();
      renderDocs();
      renderSelected();
      if (message) notify(message);
      return data.document;
    };
    const removeDocument = async documentId => {
      const document = state.docs.find(doc => doc.id === documentId);
      if (!document) return;
      if (!confirm(`确定永久删除“${document.title}”？原文件和阅读索引也会被移除。`)) return;
      await api('/api/remove', {document_id: documentId});
      state.docs = state.docs.filter(doc => doc.id !== documentId);
      state.docMenuId = null;
      if (state.selected?.id === documentId) {
        state.selected = null;
        state.reading = null;
        state.messages = [];
        state.artifacts = [];
        renderMessages();
        await showDocument();
        renderArtifacts();
      }
      renderCategoryOptions();
      renderDocs();
      renderSelected();
      notify('资料已删除');
    };
    const handleDocumentAction = async (action, documentId) => {
      const document = state.docs.find(doc => doc.id === documentId);
      if (!document) return;
      try {
        if (action === 'pin') {
          await updateDocumentOrganization(
            documentId,
            {pinned: !document.pinned},
            document.pinned ? '已取消置顶' : '已置顶'
          );
        } else if (action === 'archive') {
          await updateDocumentOrganization(
            documentId,
            {archived: !document.archived},
            document.archived ? '资料已恢复' : '资料已归档'
          );
        } else if (action === 'category') {
          state.docMenuId = null;
          state.categoryTargetId = documentId;
          $('categoryName').value = document.category || '';
          $('categoryTitle').textContent = `设置分类 · ${document.title}`;
          $('categoryModal').classList.add('open');
          requestAnimationFrame(() => $('categoryName').focus());
          renderDocs();
        } else if (action === 'delete') {
          await removeDocument(documentId);
        }
      } catch (error) {
        notify(error.message, true);
      }
    };
    const selectDocument = async id => {
      state.selected = state.docs.find(doc => doc.id === id) || null;
      state.docMenuId = null;
      state.reading = null;
      state.readingHistory = [];
      state.codeFiles = [];
      state.activeCodeId = null;
      state.codeFileCache.clear();
      state.codeLoadToken += 1;
      state.codeMarkdownEditing = false;
      state.markdownDirty = false;
      $('timelineNoteComposer').hidden = true;
      $('timelineNoteText').value = '';
      state.messages = [];
      $('analysisOutput').innerHTML = state.selected?.document_type === 'code'
        ? '<div class="empty"><div><strong>尚未解析代码项目</strong><span>将分析项目结构、模块职责、执行流程和关键实现</span></div></div>'
        : '<div class="empty"><div><strong>尚未生成阅读分析</strong><span>系统将按摘要、引言、方法、实验和结论逐节阅读</span></div></div>';
      renderDocs();
      renderSelected();
      renderMessages();
      closeArtifactWindow();
      await loadReadingState().catch(error => notify(error.message, true));
      await Promise.allSettled([showDocument(), loadArtifacts(), loadReadingHistory()]);
      if (window.innerWidth <= 680) $('library').classList.remove('open');
    };
    const renderSelected = () => {
      const doc = state.selected;
      const isCode = doc?.document_type === 'code';
      $('appShell').classList.toggle('code-mode', isCode);
      const sourceTab = document.querySelector('[data-mode="source"]');
      const analysisTab = document.querySelector('[data-mode="analysis"]');
      const searchTab = document.querySelector('[data-mode="search"]');
      sourceTab.textContent = isCode ? '代码' : '原文';
      analysisTab.textContent = isCode ? '代码解析' : '智能阅读';
      searchTab.hidden = isCode;
      $('readBtn').textContent = isCode ? '解析项目' : '阅读全文';
      $('codeDetailMode').hidden = !isCode;
      document.querySelectorAll('[data-code-detail]').forEach(button =>
        button.classList.toggle('active', button.dataset.codeDetail === state.codeDetail)
      );
      $('compareTopic').hidden = isCode;
      $('compareBtn').hidden = isCode;
      $('chatQuestion').placeholder = isCode ? '针对当前代码项目提问' : '针对当前论文提问';
      if (isCode && state.mode === 'search') setMode('source');
      if (isCode) {
        document.querySelectorAll('.inspector-tab').forEach(item =>
          item.classList.toggle('active', item.dataset.inspectorPanel === 'digest')
        );
        document.querySelectorAll('.inspector-panel').forEach(panel =>
          panel.classList.toggle('active', panel.id === 'inspector-digest')
        );
      }
      $('selectedTitle').textContent = doc?.title || '尚未选择论文';
      $('selectedMeta').textContent = doc
        ? `${doc.field || '未分类'} · ${typeLabel(doc.document_type)} · ${doc.id}`
        : '从左侧资料库选择一篇论文';
      $('topTitle').textContent = doc?.title || '论文阅读工作台';
      $('removeBtn').disabled = !doc;
      updateGenerationControls();
    };
    const showDocument = async () => {
      $('sourceToolbar').hidden = true;
      $('view-source').classList.add('no-toolbar');
      $('pdfReader').hidden = true;
      $('pdfReader').innerHTML = '';
      $('textPaper').hidden = true;
      $('markdownWorkspace').hidden = true;
      $('codeWorkspace').hidden = true;
      $('sourceEmpty').hidden = false;
      state.currentPage = 0;
      state.pageCount = 0;
      if (!state.selected) return;
      if (state.selected.document_type === 'code') {
        $('sourceEmpty').hidden = true;
        await showCodeWorkspace();
        return;
      }
      const suffix = (state.selected.path || '').split('.').pop().toLowerCase();
      $('sourceEmpty').hidden = true;
      if (suffix === 'pdf') {
        await showPdfDocument();
        return;
      }
      const data = await get(`/api/document-content?id=${encodeURIComponent(state.selected.id)}`);
      if (['md', 'markdown'].includes(suffix)) {
        showMarkdownDocument(data.text || '');
        return;
      }
      $('textPaper').textContent = data.text || '没有可显示的文本内容';
      $('textPaper').hidden = false;
    };
    const showMarkdownDocument = text => {
      $('markdownEditor').value = text;
      state.markdownDirty = false;
      $('markdownSaveState').textContent = '';
      $('markdownWorkspace').hidden = false;
      setMarkdownMode('edit');
    };
    const setMarkdownMode = mode => {
      const preview = mode === 'preview';
      $('markdownEditor').hidden = preview;
      $('markdownPreview').hidden = !preview;
      if (preview) {
        $('markdownPreview').innerHTML = formatMarkdown($('markdownEditor').value);
        highlightCode($('markdownPreview'));
        renderMathInNode($('markdownPreview'));
      }
      $('markdownEditMode').classList.toggle('primary', !preview);
      $('markdownPreviewMode').classList.toggle('primary', preview);
    };
    const showCodeWorkspace = async () => {
      const documentId = state.selected.id;
      const data = await get(`/api/code-workspace?id=${encodeURIComponent(documentId)}`);
      if (!state.selected || state.selected.id !== documentId) return;
      state.codeFiles = data.files || [];
      state.activeCodeId = data.selected_id || state.codeFiles[0]?.id || null;
      $('codeProjectTitle').textContent = data.project || '代码';
      $('codeWorkspace').hidden = false;
      renderCodeTree();
      await renderCodeFile(state.activeCodeId);
    };
    const renderCodeTree = () => {
      const rows = [];
      const seenDirectories = new Set();
      state.codeFiles.forEach(file => {
        const parts = String(file.path || file.title).split('/');
        parts.slice(0, -1).forEach((part, index) => {
          const key = parts.slice(0, index + 1).join('/');
          if (seenDirectories.has(key)) return;
          seenDirectories.add(key);
          rows.push({
            kind: 'directory',
            key,
            name: part,
            depth: index
          });
        });
        rows.push({
          kind: 'file',
          id: file.id,
          key: file.path,
          name: parts.at(-1),
          depth: Math.max(0, parts.length - 1)
        });
      });
      $('codeTree').innerHTML = rows.map(row => row.kind === 'directory' ? `
        <div class="code-tree-item" style="padding-left:${10 + row.depth * 14}px">
          <span class="code-tree-icon">▾</span><span>${escapeHtml(row.name)}</span>
        </div>
      ` : `
        <button class="code-tree-item ${state.activeCodeId === row.id ? 'active' : ''}"
          data-code-id="${escapeHtml(row.id)}" style="padding-left:${10 + row.depth * 14}px">
          <span class="code-tree-icon">◇</span><span>${escapeHtml(row.name)}</span>
        </button>
      `).join('');
      document.querySelectorAll('[data-code-id]').forEach(button => {
        button.onclick = () => renderCodeFile(button.dataset.codeId);
      });
    };
    const renderCodeFile = async id => {
      const metadata = state.codeFiles.find(item => item.id === id);
      if (!metadata) return;
      const token = ++state.codeLoadToken;
      state.activeCodeId = id;
      state.codeMarkdownEditing = false;
      $('codeTabTitle').textContent = metadata.path || metadata.title;
      $('editCodeMarkdown').hidden = !metadata.editable;
      $('saveCodeMarkdown').hidden = true;
      $('codeContent').innerHTML = '<div class="empty"><div><strong>正在加载文件</strong></div></div>';
      renderCodeTree();
      let file = state.codeFileCache.get(id);
      if (!file) {
        const data = await get(`/api/code-file?id=${encodeURIComponent(id)}`);
        if (token !== state.codeLoadToken) return;
        file = data.file;
        state.codeFileCache.set(id, file);
        while (state.codeFileCache.size > 8) {
          state.codeFileCache.delete(state.codeFileCache.keys().next().value);
        }
      }
      if (token !== state.codeLoadToken) return;
      if (file.kind === 'notebook') {
        $('codeContent').innerHTML = `<div class="notebook-view">${(file.cells || []).map(cell => `
          <article class="notebook-cell ${escapeHtml(cell.type)}">
            <div class="notebook-prompt">${cell.type === 'code' ? `In [${cell.execution_count ?? ' '}]` : ''}</div>
            <div class="notebook-cell-body">
              ${cell.type === 'code'
                ? `<pre><code class="language-${escapeHtml(cell.language || 'python')}">${escapeHtml(cell.content || '')}</code></pre>`
                : formatNotebookMarkdown(cell.content || '')}
              ${(cell.outputs || []).map(output => `<div class="notebook-output">${escapeHtml(output)}</div>`).join('')}
            </div>
          </article>
        `).join('')}</div>`;
      } else {
        $('codeContent').innerHTML = `<pre><code class="language-${escapeHtml(file.language || 'plaintext')}">${escapeHtml(file.content || '')}</code></pre>`;
      }
      highlightCode($('codeContent'));
    };
    const highlightCode = container => {
      const run = () => {
        if (!window.hljs) return false;
        container.querySelectorAll('pre code').forEach(node => window.hljs.highlightElement(node));
        return true;
      };
      if (!run()) window.setTimeout(run, 300);
    };
    const formatMarkdown = value => {
      const math = tokenizeMath(value);
      const source = escapeHtml(math.text);
      const fenced = [];
      const withoutFences = source.replace(/```([a-z0-9_-]*)\n([\s\S]*?)```/gi, (_match, language, code) => {
        const token = `@@CODE_BLOCK_${fenced.length}@@`;
        fenced.push(`<pre><code class="language-${language || 'plaintext'}">${code.replace(/\n$/, '')}</code></pre>`);
        return token;
      });
      const lines = withoutFences.split('\n');
      const output = [];
      let listOpen = false;
      lines.forEach(line => {
        if (/^@@CODE_BLOCK_\d+@@$/.test(line)) {
          if (listOpen) { output.push('</ul>'); listOpen = false; }
          output.push(line);
          return;
        }
        const heading = line.match(/^(#{1,3})\s+(.+)$/);
        const listItem = line.match(/^[-*]\s+(.+)$/);
        if (heading) {
          if (listOpen) { output.push('</ul>'); listOpen = false; }
          const level = heading[1].length;
          output.push(`<h${level}>${heading[2]}</h${level}>`);
        } else if (listItem) {
          if (!listOpen) { output.push('<ul>'); listOpen = true; }
          output.push(`<li>${listItem[1]}</li>`);
        } else if (line.trim()) {
          if (listOpen) { output.push('</ul>'); listOpen = false; }
          const inline = line
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`]+)`/g, '<code>$1</code>');
          output.push(`<p>${inline}</p>`);
        }
      });
      if (listOpen) output.push('</ul>');
      const html = output.join('').replace(
        /@@CODE_BLOCK_(\d+)@@/g,
        (_match, index) => fenced[Number(index)] || ''
      );
      return math.restore(html);
    };
    const researchList = values => {
      const items = (Array.isArray(values) ? values : []).filter(Boolean);
      return items.length
        ? `<ul>${items.map(item => `<li>${escapeHtml(typeof item === 'string' ? item : JSON.stringify(item))}</li>`).join('')}</ul>`
        : '';
    };
    const checkedResearchValues = selector => [...document.querySelectorAll(selector)]
      .filter(input => input.checked)
      .map(input => input.value);
    const selectedResearchPaperIds = () => checkedResearchValues('input[name="research-paper"]');
    const selectedResearchCodeIds = () => [...document.querySelectorAll('input[name="research-code"]:checked')]
      .flatMap(input => String(input.dataset.ids || '').split('|').filter(Boolean));
    const selectedResearchCandidates = () => {
      const selected = new Set(checkedResearchValues('input[name="research-candidate"]'));
      return state.researchCandidates.filter(item => selected.has(String(item.id)));
    };
    const renderResearchTaskSelect = () => {
      const current = state.researchTask?.id || '';
      $('researchTaskSelect').innerHTML = '<option value="">选择任务</option>' + state.researchTasks.map(task => {
        const label = task.name || task.direction || `任务 ${task.id}`;
        return `<option value="${escapeHtml(task.id)}">${escapeHtml(label.slice(0, 55))}</option>`;
      }).join('');
      $('researchTaskSelect').value = current;
    };
    const renderResearchMaterialChoices = () => {
      const paperIds = new Set(state.researchTask?.paper_ids || []);
      const papers = state.docs.filter(doc => doc.document_type === 'paper' && !doc.archived);
      $('researchPaperChoices').innerHTML = papers.length ? papers.map(doc => `
        <label class="research-choice">
          <input type="checkbox" name="research-paper" value="${escapeHtml(doc.id)}" ${paperIds.has(doc.id) ? 'checked' : ''}>
          <span>${escapeHtml(doc.title)}<small>${escapeHtml(doc.category || doc.field || '未分类')}</small></span>
        </label>
      `).join('') : '<div class="research-empty">资料库中还没有论文。</div>';

      const selectedCodeIds = new Set(state.researchTask?.code_ids || []);
      const codeDocs = state.docs.filter(doc => doc.document_type === 'code' && !doc.archived);
      const projects = new Map();
      codeDocs.forEach(doc => {
        const key = doc.category || doc.id;
        if (!projects.has(key)) projects.set(key, []);
        projects.get(key).push(doc);
      });
      $('researchCodeChoices').innerHTML = projects.size ? [...projects.entries()].map(([key, docs]) => {
        const ids = docs.map(doc => doc.id);
        const title = docs[0].category || docs[0].title;
        const checked = ids.every(id => selectedCodeIds.has(id));
        return `
          <label class="research-choice">
            <input type="checkbox" name="research-code" data-ids="${escapeHtml(ids.join('|'))}" ${checked ? 'checked' : ''}>
            <span>${escapeHtml(title)}<small>${docs.length} 个文件</small></span>
          </label>
        `;
      }).join('') : '<div class="research-empty">资料库中还没有代码项目。</div>';
      $('researchCorrespondence').disabled = !state.researchTask
        || paperIds.size === 0
        || selectedCodeIds.size === 0;
    };
    const renderResearchCandidates = () => {
      const selected = new Set(
        (state.researchTask?.selected_related?.length
          ? state.researchTask.selected_related
          : state.researchCandidates
        ).map(item => String(item.id))
      );
      const sortMode = $('researchCandidateSort').value || 'relevance';
      const candidates = [...state.researchCandidates];
      if (sortMode === 'newest') {
        candidates.sort((left, right) =>
          String(right.published || '').localeCompare(String(left.published || ''))
        );
      } else if (sortMode === 'oldest') {
        candidates.sort((left, right) =>
          String(left.published || '9999').localeCompare(String(right.published || '9999'))
        );
      }
      $('researchCandidateList').innerHTML = candidates.length
        ? candidates.map(item => `
          <div class="research-candidate">
            <input type="checkbox" name="research-candidate" value="${escapeHtml(item.id)}"
              ${item.imported_document_id ? 'disabled' : (selected.has(String(item.id)) ? 'checked' : '')}>
            <span>
              <strong>${escapeHtml(item.title)}</strong>
              <p>${escapeHtml(item.brief_summary || String(item.summary || '').slice(0, 240))}</p>
              <span class="research-candidate-meta">${escapeHtml((item.authors || []).slice(0, 4).join(', '))}${item.published ? ` · ${escapeHtml(item.published)}` : ''}</span>
            </span>
            <button class="btn research-candidate-action" data-import-candidate="${escapeHtml(item.id)}"
              ${item.imported_document_id ? 'disabled' : ''}>
              ${item.imported_document_id ? t('已导入', 'Imported') : t('导入资料库', 'Import')}
            </button>
          </div>
        `).join('')
        : '<div class="research-empty">尚未发现外部论文。已有本地论文时，仍可直接进行综合分析。</div>';
      document.querySelectorAll('[data-import-candidate]').forEach(button => {
        button.onclick = () => importResearchCandidate(button.dataset.importCandidate);
      });
      $('researchAnalyze').disabled = !state.researchTask;
    };
    const renderResearchAnalysis = () => {
      const analysis = state.researchAnalysis;
      if (!analysis) {
        $('researchAnalysisOutput').innerHTML = '<div class="research-empty">完成论文选择后，这里会给出跨论文综合、代码对应关系和可验证的后续方向。</div>';
        $('researchPlan').disabled = true;
        $('researchDirectionIndex').innerHTML = '<option value="">由 Agent 判断</option>';
        return;
      }
      const synthesis = analysis.cross_paper_synthesis || {};
      const papers = (analysis.paper_assessments || []).map(item => `
        <div class="research-paper-result">
          <h4>${escapeHtml(item.title || '论文')}</h4>
          <span class="research-status">${escapeHtml(item.source_level || '')}</span>
          ${item.relevance ? `<p><strong>相关性：</strong>${escapeHtml(item.relevance)}</p>` : ''}
          ${researchList(item.innovations)}
          ${item.limitations?.length ? `<p><strong>不足：</strong></p>${researchList(item.limitations)}` : ''}
        </div>
      `).join('');
      const directions = (analysis.future_directions || []).map((item, index) => `
        <div class="research-paper-result">
          <h4>${index + 1}. ${escapeHtml(item.direction || '后续方向')}</h4>
          <p>${escapeHtml(item.rationale || '')}</p>
          ${item.minimal_test ? `<p><strong>最小验证：</strong>${escapeHtml(item.minimal_test)}</p>` : ''}
          ${item.risk ? `<p><strong>风险：</strong>${escapeHtml(item.risk)}</p>` : ''}
        </div>
      `).join('');
      $('researchAnalysisOutput').innerHTML = `
        <h4>总体判断</h4><p>${escapeHtml(analysis.overview || '')}</p>
        ${papers}
        <h4>共同基础</h4>${researchList(synthesis.common_ground)}
        <h4>关键差异</h4>${researchList(synthesis.key_differences)}
        <h4>尚未解决的问题</h4>${researchList(synthesis.unresolved_gaps)}
        <h4>可行的后续工作</h4>${directions || '<p>没有形成可验证的后续方向。</p>'}
        ${analysis.recommendation ? `<h4>建议</h4><p>${escapeHtml(analysis.recommendation)}</p>` : ''}
        ${analysis.evidence_limits?.length ? `<h4>证据边界</h4>${researchList(analysis.evidence_limits)}` : ''}
      `;
      $('researchDirectionIndex').innerHTML = '<option value="">由 Agent 判断</option>' +
        (analysis.future_directions || []).map((item, index) =>
          `<option value="${index}">${index + 1}. ${escapeHtml(item.direction || '后续方向')}</option>`
        ).join('');
      $('researchPlan').disabled = false;
    };
    const correspondenceStatusLabel = status => ({
      implemented: t('已实现', 'Implemented'),
      partial: t('部分实现', 'Partial'),
      missing: t('缺失', 'Missing'),
      uncertain: t('无法确认', 'Uncertain')
    }[status] || status);
    const renderResearchCorrespondence = () => {
      const report = state.researchCorrespondence;
      const output = $('researchCorrespondenceOutput');
      if (!report) {
        output.innerHTML = '<div class="research-empty">选择至少一篇本地论文和一个代码项目后，检查算法、公式、数据处理、参数、指标与实验配置的实现情况。</div>';
        return;
      }
      const counts = report.status_counts || {};
      const codeCoverage = report.code_coverage || {};
      const coverageLabel = codeCoverage.is_exhaustive
        ? t('已检查全部可读代码文件', 'All readable code files checked')
        : t(
            `按论文要求检索了 ${Number(codeCoverage.scanned_files || 0)} 个文件，送入 ${Number(codeCoverage.selected_files || 0)} 个最相关文件；未命中不等于缺失`,
            `Searched ${Number(codeCoverage.scanned_files || 0)} files and inspected ${Number(codeCoverage.selected_files || 0)} relevant files; no match does not prove absence`
          );
      const checks = (report.checks || []).map(item => {
        const locations = (item.code_locations || []).map(location => {
          const symbols = (location.symbols || []).map(symbol => symbol.name).filter(Boolean);
          return `
            <div class="code-location">
              ${escapeHtml(location.path || 'unknown')} · L${escapeHtml(location.line_start || '?')}-${escapeHtml(location.line_end || '?')}
              ${symbols.length ? `<br>${escapeHtml(symbols.join(', '))}` : ''}
            </div>
          `;
        }).join('');
        return `
          <div class="correspondence-check">
            <div class="correspondence-check-head">
              <strong>${escapeHtml(item.paper_claim || '论文要求')}</strong>
              <span class="research-status ${escapeHtml(item.status || 'uncertain')}">${escapeHtml(correspondenceStatusLabel(item.status))}</span>
              <span class="research-status">${escapeHtml(item.category || '')}</span>
            </div>
            ${item.paper_citation
              ? `<p><span class="citation">${escapeHtml(item.paper_citation)}</span></p>`
              : '<p class="muted">未通过论文引用校验</p>'}
            ${item.expected_behavior ? `<p><strong>预期行为：</strong>${escapeHtml(item.expected_behavior)}</p>` : ''}
            ${locations}
            ${item.implementation_evidence ? `<p><strong>实现证据：</strong>${escapeHtml(item.implementation_evidence)}</p>` : ''}
            ${item.discrepancy ? `<p><strong>差异：</strong>${escapeHtml(item.discrepancy)}</p>` : ''}
            ${item.verification_action ? `<p><strong>验证动作：</strong>${escapeHtml(item.verification_action)}</p>` : ''}
          </div>
        `;
      }).join('');
      output.innerHTML = `
        <p>${escapeHtml(report.summary || '')}</p>
        <p class="muted">${escapeHtml(coverageLabel)}</p>
        <div class="correspondence-summary">
          <div class="correspondence-metric"><strong>${Number(report.coverage_percent || 0)}%</strong><span>可定位覆盖</span></div>
          <div class="correspondence-metric"><strong>${Number(counts.implemented || 0)}</strong><span>已实现</span></div>
          <div class="correspondence-metric"><strong>${Number(counts.partial || 0)}</strong><span>部分实现</span></div>
          <div class="correspondence-metric"><strong>${Number(counts.missing || 0)}</strong><span>缺失</span></div>
          <div class="correspondence-metric"><strong>${Number(counts.uncertain || 0)}</strong><span>无法确认</span></div>
        </div>
        ${checks || '<div class="research-empty">没有形成可验证的对应检查项。</div>'}
        ${report.missing_components?.length ? `<h4>缺失组件</h4>${researchList(report.missing_components)}` : ''}
        ${report.unverified_absence_candidates?.length ? `<h4>${escapeHtml(t('未覆盖全库，以下仅为待检项', 'Full repository not covered; candidates for further checking'))}</h4>${researchList(report.unverified_absence_candidates)}` : ''}
        ${report.reproduction_risks?.length ? `<h4>复现风险</h4>${researchList(report.reproduction_risks)}` : ''}
        ${report.recommended_next_checks?.length ? `<h4>建议的下一步检查</h4>${researchList(report.recommended_next_checks)}` : ''}
      `;
    };
    const renderResearchExperiment = () => {
      const experiment = state.researchExperiment;
      if (!experiment) {
        $('researchExperimentOutput').innerHTML = '';
        $('researchPromptArea').hidden = true;
        $('researchAssess').disabled = true;
        return;
      }
      $('researchExperimentOutput').innerHTML = `
        <h4>${escapeHtml(experiment.title || '实验方案')}</h4>
        <p><strong>假设：</strong>${escapeHtml(experiment.hypothesis || '')}</p>
        <p><strong>范围：</strong>${escapeHtml(experiment.scope || '')}</p>
        <h4>实施步骤</h4>${researchList(experiment.implementation_steps)}
        <h4>测量指标</h4>${researchList(experiment.measurements)}
        <h4>成功标准</h4>${researchList(experiment.success_criteria)}
        <h4>中止条件</h4>${researchList(experiment.stop_conditions)}
      `;
      $('researchPrompt').value = experiment.codex_prompt || '';
      $('researchPromptArea').hidden = false;
      $('researchAssess').disabled = false;
    };
    const renderResearchAttachments = () => {
      state.researchAttachments = state.researchTask?.result_attachments || [];
      $('researchAttachmentList').innerHTML = state.researchAttachments.map(item => {
        const image = item.kind === 'image';
        const status = image
          ? ({
              analyzed: t('视觉模型已解析', 'Analyzed by vision model'),
              not_configured: t('尚未配置视觉模型', 'Vision model not configured'),
              failed: t('视觉解析失败', 'Vision analysis failed')
            }[item.vision_status] || t('图片', 'Image'))
          : t('Markdown 已读取', 'Markdown loaded');
        return `
          <div class="research-attachment">
            ${image
              ? `<img src="/api/research-attachment?task_id=${encodeURIComponent(state.researchTask.id)}&attachment_id=${encodeURIComponent(item.id)}" alt="${escapeHtml(item.filename)}">`
              : '<span class="research-attachment-icon">MD</span>'}
            <span>
              <strong>${escapeHtml(item.filename || 'attachment')}</strong>
              <span>${escapeHtml(status)}</span>
            </span>
          </div>
        `;
      }).join('');
    };
    const renderResearchAssessment = assessment => {
      if (!assessment) {
        $('researchAssessmentOutput').innerHTML = '';
        return;
      }
      const decision = ['continue', 'adjust', 'stop'].includes(assessment.decision)
        ? assessment.decision
        : 'adjust';
      $('researchAssessmentOutput').innerHTML = `
        <h4><span class="research-status ${decision}">${escapeHtml(decision)}</span></h4>
        <p>${escapeHtml(assessment.rationale || '')}</p>
        ${researchList(assessment.observations)}
        ${assessment.failure_classification ? `<p><strong>问题分类：</strong>${escapeHtml(assessment.failure_classification)}</p>` : ''}
        ${assessment.revised_hypothesis ? `<p><strong>修正假设：</strong>${escapeHtml(assessment.revised_hypothesis)}</p>` : ''}
        ${assessment.next_measurements?.length ? `<h4>下一轮测量</h4>${researchList(assessment.next_measurements)}` : ''}
        ${assessment.stop_reason ? `<p><strong>中止原因：</strong>${escapeHtml(assessment.stop_reason)}</p>` : ''}
      `;
      if (assessment.revised_codex_prompt) {
        $('researchPrompt').value = assessment.revised_codex_prompt;
        $('researchPromptArea').hidden = false;
      }
    };
    const applyResearchTask = task => {
      state.researchTask = task || null;
      state.researchCandidates = task?.related_candidates || [];
      state.researchAnalysis = task?.analysis || null;
      state.researchCorrespondence = task?.correspondence || null;
      state.researchExperiment = task?.experiment || null;
      state.researchAttachments = task?.result_attachments || [];
      $('researchCandidateSort').value = task?.candidate_sort || 'relevance';
      $('researchTaskName').value = task?.name || '';
      $('researchTaskName').disabled = !task;
      $('researchDirection').value = task?.direction || '';
      $('researchPromptAppend').value = '';
      $('researchResult').value = '';
      renderResearchTaskSelect();
      renderResearchMaterialChoices();
      renderResearchCandidates();
      renderResearchAnalysis();
      renderResearchCorrespondence();
      renderResearchExperiment();
      renderResearchAttachments();
      renderResearchAssessment(task?.decisions?.length ? task.decisions[task.decisions.length - 1] : null);
    };
    const loadResearchTasks = async (selectLatest=false) => {
      const data = await get('/api/research-tasks?limit=20');
      state.researchTasks = data.tasks || [];
      if (state.researchTask) {
        const updated = state.researchTasks.find(task => task.id === state.researchTask.id);
        if (updated) state.researchTask = updated;
      } else if (selectLatest && state.researchTasks.length) {
        state.researchTask = state.researchTasks[0];
      }
      applyResearchTask(state.researchTask);
    };
    const formatNotebookMarkdown = formatMarkdown;
    const showPdfDocument = async () => {
      const documentId = state.selected.id;
      const manifest = await get(`/api/document-pages?id=${encodeURIComponent(documentId)}`);
      if (!state.selected || state.selected.id !== documentId) return;
      state.pageCount = Number(manifest.page_count || 0);
      const reader = $('pdfReader');
      reader.innerHTML = (manifest.pages || []).map(page => `
        <article class="pdf-page" data-page="${page.page}" style="aspect-ratio:${page.width}/${page.height}">
          <img loading="lazy"
            src="/api/artifact-page-image?id=${encodeURIComponent(documentId)}&page=${page.page}"
            alt="第 ${page.page} 页">
          <div class="pdf-text-layer" data-text-page="${page.page}" aria-label="第 ${page.page} 页文本"></div>
          <span class="pdf-page-number">${page.page}</span>
        </article>
      `).join('');
      $('sourceToolbar').hidden = false;
      $('view-source').classList.remove('no-toolbar');
      $('pageJump').max = String(state.pageCount);
      $('pageTotal').textContent = `/ ${state.pageCount}`;
      reader.hidden = false;
      reader.onscroll = scheduleVisiblePageUpdate;
      const textLayers = [...reader.querySelectorAll('.pdf-text-layer')];
      Promise.allSettled(textLayers.map(layer =>
        loadPdfTextLayer(documentId, Number(layer.dataset.textPage), layer)
      ));
      const restoredPage = Math.max(1, Math.min(state.pageCount, Number(state.reading?.current_page || 1)));
      requestAnimationFrame(() => {
        reader.querySelector(`[data-page="${restoredPage}"]`)?.scrollIntoView({block: 'start'});
        updateVisiblePage(true);
      });
    };
    const loadPdfTextLayer = async (documentId, pageNumber, layer) => {
      const data = await get(
        `/api/document-page-text?id=${encodeURIComponent(documentId)}&page=${encodeURIComponent(pageNumber)}`
      );
      if (!state.selected || state.selected.id !== documentId || !layer.isConnected) return;
      layer.innerHTML = (data.lines || []).map(line => {
        const [x0, y0, x1, y1] = line.bbox || [0, 0, 0, 0];
        return `<span class="pdf-text-line"
          style="left:${x0 * 100}%;top:${y0 * 100}%;width:${Math.max(0, x1 - x0) * 100}%;height:${Math.max(0, y1 - y0) * 100}%"
          data-height="${Math.max(0, y1 - y0)}">${escapeHtml(line.text || '')}\n</span>`;
      }).join('');
      layoutPdfTextLayer(layer);
    };
    const layoutPdfTextLayer = layer => {
      const page = layer.closest('.pdf-page');
      if (!page) return;
      const pageHeight = page.clientHeight;
      layer.querySelectorAll('.pdf-text-line').forEach(line => {
        const normalizedHeight = Number(line.dataset.height || 0);
        line.style.fontSize = `${Math.max(6, normalizedHeight * pageHeight * 0.82)}px`;
      });
    };
    const jumpToPage = value => {
      if (!state.pageCount || $('pdfReader').hidden) return;
      const page = Math.max(1, Math.min(state.pageCount, Number(value) || 1));
      $('pageJump').value = String(page);
      $('pdfReader').querySelector(`[data-page="${page}"]`)?.scrollIntoView({block: 'start', behavior: 'smooth'});
      window.setTimeout(() => updateVisiblePage(true), 220);
    };
    let pageFrame = 0;
    const scheduleVisiblePageUpdate = () => {
      cancelAnimationFrame(pageFrame);
      pageFrame = requestAnimationFrame(() => updateVisiblePage(false));
    };
    const updateVisiblePage = force => {
      const reader = $('pdfReader');
      if (reader.hidden || !state.selected || !state.pageCount) return;
      const readerRect = reader.getBoundingClientRect();
      const center = readerRect.top + readerRect.height * 0.45;
      let current = 1;
      let distance = Infinity;
      reader.querySelectorAll('.pdf-page').forEach(node => {
        const rect = node.getBoundingClientRect();
        const candidate = Math.abs((rect.top + rect.bottom) / 2 - center);
        if (candidate < distance) {
          distance = candidate;
          current = Number(node.dataset.page);
        }
      });
      if (!force && current === state.currentPage) return;
      state.currentPage = current;
      const maxReached = Math.max(Number(state.reading?.max_page_reached || 0), current);
      state.reading = {
        ...(state.reading || {}),
        current_page: current,
        page_count: state.pageCount,
        max_page_reached: maxReached,
        progress_percent: Math.round(current / state.pageCount * 100)
      };
      renderReadingState();
      clearTimeout(state.progressSaveTimer);
      state.progressSaveTimer = setTimeout(saveReadingPosition, 650);
    };
    const saveReadingPosition = async () => {
      if (!state.selected || !state.currentPage || !state.pageCount) return;
      const documentId = state.selected.id;
      try {
        const data = await api('/api/progress', {
          ...requireDoc(),
          status: state.currentPage >= state.pageCount ? 'done' : 'reading',
          current_page: state.currentPage,
          page_count: state.pageCount
        });
        if (state.selected?.id === documentId) {
          state.reading = data.state;
          renderReadingState();
        }
      } catch (error) {
        notify(`阅读位置自动保存失败：${error.message}`, true);
      }
    };
    const setMode = mode => {
      state.mode = mode;
      document.querySelectorAll('.mode-tab').forEach(tab => tab.classList.toggle('active', tab.dataset.mode === mode));
      document.querySelectorAll('.view').forEach(view => view.classList.toggle('active', view.id === `view-${mode}`));
    };

    const loadReadingState = async () => {
      if (!state.selected) return;
      const data = await api('/api/state', requireDoc());
      state.reading = data.state;
      renderReadingState();
    };
    const loadReadingHistory = async () => {
      if (!state.selected) {
        state.readingHistory = [];
        renderReadingDigest();
        return;
      }
      const documentId = state.selected.id;
      const data = await get(`/api/reading-history?id=${encodeURIComponent(documentId)}`);
      if (!state.selected || state.selected.id !== documentId) return;
      state.readingHistory = data.entries || [];
      renderReadingDigest();
      restoreLatestGeneratedViews();
    };
    const timelineKindLabel = kind => ({
      note: t('笔记', 'Note'),
      question: t('问答', 'Q&A'),
      smart_reading: t('智能阅读', 'Smart Reading'),
      code_analysis: t('代码解析', 'Code Analysis'),
      artifact_explanation: t('图表解释', 'Artifact'),
      evidence_search: t('证据检索', 'Evidence Search'),
      timeline_summary: t('总结', 'Summary')
    }[kind] || kind || t('记录', 'Record'));
    const timelinePreview = entry => {
      if (entry.summary) return entry.summary;
      if (entry.kind === 'question') return _compactTimelineText(entry.answer || entry.text);
      if (entry.kind === 'note') return _compactTimelineText(entry.text);
      if (entry.kind === 'evidence_search') {
        return `${entry.metadata?.result_count || 0} ${t('条结果', 'results')}`;
      }
      return _compactTimelineText(entry.answer || entry.text);
    };
    const _compactTimelineText = value => String(value || '')
      .replace(/[#*`_[\]{}]/g, '')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 96);
    const renderReadingDigest = () => {
      const entries = state.readingHistory;
      $('readingDigestText').innerHTML = entries.map((entry, index) => {
        const created = entry.created_at ? new Date(entry.created_at).toLocaleString() : '';
        const title = entry.kind === 'note' ? '' : (entry.text || entry.question || '');
        const editable = Boolean(entry.id && entry.id !== 'personal-note');
        return `
        <article class="digest-entry" data-history-index="${index}" data-entry-id="${escapeHtml(entry.id || '')}" draggable="${editable}">
          <button class="digest-open" data-history-index="${index}">
            <span class="digest-entry-head">
              <span class="digest-entry-kind">${escapeHtml(timelineKindLabel(entry.kind))}</span>
              ${title ? `<span class="digest-entry-title">${escapeHtml(title)}</span>` : ''}
            </span>
            <span class="digest-entry-preview">${escapeHtml(timelinePreview(entry))}</span>
            ${created ? `<span class="digest-entry-time">${escapeHtml(created)}</span>` : ''}
          </button>
          ${editable ? `
            <span class="digest-entry-actions">
              <button class="digest-entry-action digest-drag" title="拖动排序" aria-label="拖动排序">⋮⋮</button>
              <button class="digest-entry-action delete" data-delete-entry="${escapeHtml(entry.id)}" title="删除记录" aria-label="删除记录">×</button>
            </span>
          ` : ''}
        </article>
      `;
      }).join('');
      $('readingDigestEmpty').hidden = entries.length > 0;
      document.querySelectorAll('.digest-open').forEach(button => {
        button.onclick = () => openReadingHistory(Number(button.dataset.historyIndex));
      });
      document.querySelectorAll('.digest-entry[draggable="true"]').forEach(entry => {
        entry.ondragstart = event => {
          state.draggedTimelineId = entry.dataset.entryId;
          entry.classList.add('dragging');
          event.dataTransfer.effectAllowed = 'move';
          event.dataTransfer.setData('text/plain', state.draggedTimelineId);
        };
        entry.ondragend = () => {
          state.draggedTimelineId = null;
          document.querySelectorAll('.digest-entry').forEach(item =>
            item.classList.remove('dragging', 'drop-target')
          );
        };
        entry.ondragover = event => {
          if (!state.draggedTimelineId || state.draggedTimelineId === entry.dataset.entryId) return;
          event.preventDefault();
          entry.classList.add('drop-target');
        };
        entry.ondragleave = () => entry.classList.remove('drop-target');
        entry.ondrop = async event => {
          event.preventDefault();
          entry.classList.remove('drop-target');
          const draggedId = state.draggedTimelineId || event.dataTransfer.getData('text/plain');
          const targetId = entry.dataset.entryId;
          if (!draggedId || !targetId || draggedId === targetId) return;
          const ids = state.readingHistory.filter(item => item.id && item.id !== 'personal-note').map(item => item.id);
          const from = ids.indexOf(draggedId);
          const to = ids.indexOf(targetId);
          if (from < 0 || to < 0) return;
          ids.splice(to, 0, ids.splice(from, 1)[0]);
          try {
            const data = await api('/api/timeline-reorder', {...requireDoc(), entry_ids: ids});
            state.reading = data.state;
            await loadReadingHistory();
          } catch (error) { notify(error.message, true); }
        };
      });
      document.querySelectorAll('[data-delete-entry]').forEach(button => {
        button.onclick = async event => {
          event.stopPropagation();
          if (!window.confirm(t('确定删除这条阅读记录？', 'Delete this reading record?'))) return;
          try {
            const data = await api('/api/timeline-delete', {
              ...requireDoc(),
              entry_id: button.dataset.deleteEntry
            });
            state.reading = data.state;
            await loadReadingHistory();
          } catch (error) { notify(error.message, true); }
        };
      });
      updateGenerationControls();
    };
    const updateGenerationControls = () => {
      if (!$('regenerateAnalysis')) return;
      const targetKind = state.selected?.document_type === 'code' ? 'code_analysis' : 'smart_reading';
      $('regenerateAnalysis').hidden = !state.readingHistory.some(entry => entry.kind === targetKind);
    };
    const restoreLatestGeneratedViews = () => {
      const latestAnalysis = [...state.readingHistory].reverse().find(entry =>
        entry.kind === (state.selected?.document_type === 'code' ? 'code_analysis' : 'smart_reading')
      );
      if (latestAnalysis?.answer) {
        beginStreamingAnalysis();
        finalizeStreamingReport(latestAnalysis.answer);
        $('streamCursor')?.remove();
        if ($('streamStatus')) $('streamStatus').textContent = t('已载入最近一次生成记录', 'Loaded the latest saved generation');
      }
      const latestSearch = [...state.readingHistory].reverse().find(entry => entry.kind === 'evidence_search');
      if (latestSearch?.answer) {
        try { renderSearch(JSON.parse(latestSearch.answer)); } catch (_error) {}
      }
    };
    const openReadingHistory = index => {
      const entry = state.readingHistory[index];
      if (!entry) return;
      $('historyQuestion').textContent = `${timelineKindLabel(entry.kind)} · ${entry.text || entry.question || ''}`;
      if (entry.kind === 'evidence_search') {
        try {
          $('historyAnswer').innerHTML = searchResultsMarkup(JSON.parse(entry.answer || '{}'));
        } catch (_error) {
          $('historyAnswer').textContent = entry.answer || '';
        }
      } else {
        $('historyAnswer').innerHTML = formatMessageText(entry.answer || entry.text || '');
      }
      $('historyModal').classList.add('open');
      renderMathInNode($('historyAnswer'));
    };
    const renderReadingState = () => {
      const reading = state.reading || {};
      const percent = Math.max(0, Math.min(100, Number(reading.progress_percent || 0)));
      $('progressPercentLabel').textContent = `${percent}%`;
      $('progressFill').style.width = `${percent}%`;
      const currentPage = Number(reading.current_page || state.currentPage || 0);
      const pageCount = Number(reading.page_count || state.pageCount || 0);
      if (currentPage) $('pageJump').value = String(currentPage);
      $('readingPageLabel').textContent = currentPage && pageCount
        ? `第 ${currentPage} / ${pageCount} 页 · 自动保存`
        : '尚未开始阅读';
      renderReadingDigest();
    };

    const renderAnalysis = payload => {
      const data = payload.data || payload;
      const coverage = data.coverage || {};
      const synthesis = data.synthesis || {};
      const sections = synthesis.sections || [];
      $('analysisOutput').innerHTML = `
        <h2 class="output-title">全文阅读结果</h2>
        <div class="coverage">
          <strong>${coverage.covered_count || 0}/${coverage.total_count || 0}</strong>
          <span>章节证据已覆盖</span>
          ${coverage.missing_roles?.length ? `<span>缺失：${escapeHtml(coverage.missing_roles.map(roleLabel).join('、'))}</span>` : ''}
        </div>
        ${sections.map(section => `
          <article class="section-block">
            <div class="section-heading">
              <h3>${escapeHtml(section.label || '')}</h3>
              ${section.supported ? '' : '<span class="tag warn">证据不足</span>'}
            </div>
            <div class="analysis-text">${escapeHtml(section.text || '')}</div>
            ${(section.citations || []).map(citation => `
              <div class="citation">${escapeHtml(citation)}</div>
            `).join('')}
          </article>
        `).join('') || '<div class="muted">没有生成可用的全文分析</div>'}
      `;
      if (data.reading_state) {
        state.reading = data.reading_state;
        renderReadingState();
      }
    };
    const beginStreamingAnalysis = () => {
      const isCode = state.selected?.document_type === 'code';
      $('analysisOutput').innerHTML = `
        <h2 class="output-title">${isCode ? '代码解析结果' : '全文阅读结果'}</h2>
        <div class="coverage" id="streamCoverage">
          <strong>...</strong><span>${isCode ? '正在读取项目结构' : '正在整理章节证据'}</span>
        </div>
        <div class="stream-status" id="streamStatus">${isCode ? '正在准备代码上下文...' : '正在准备原文...'}</div>
        <div class="stream-report" id="streamReport"></div>
        <span class="stream-cursor" id="streamCursor"></span>
      `;
    };
    const finalizeStreamingReport = text => {
      const report = $('streamReport');
      if (!report) return;
      if (state.selected?.document_type === 'code') {
        report.innerHTML = formatMarkdown(text);
        highlightCode(report);
        renderMathInNode(report);
        return;
      }
      const firstHeading = text.indexOf('【');
      if (firstHeading >= 0) text = text.slice(firstHeading);
      const headingPattern = /(【[^】]+】)/g;
      const parts = text.split(headingPattern).filter(Boolean);
      const formatParagraph = paragraph => {
        const math = tokenizeMath(paragraph.trim());
        const html = escapeHtml(math.text)
          .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
          .replace(/`([^`\n]+)`/g, '<code>$1</code>')
          .replace(
            /(\[[^\[\]\n]+\|[^\[\]\n]+\])/g,
            '<span class="citation inline-citation">$1</span>'
          )
          .replace(/\n/g, '<br>');
        return math.restore(html);
      };
      report.innerHTML = parts.map(part => {
        if (/^【[^】]+】$/.test(part)) {
          return `<h3>${escapeHtml(part.slice(1, -1))}</h3>`;
        }
        return part.split(/\n{2,}/).filter(Boolean)
          .map(paragraph => `<p>${formatParagraph(paragraph)}</p>`).join('');
      }).join('');
      renderMathInNode(report);
    };
    const streamRead = async (payload, signal=null) => {
      const response = await fetch('/api/read-stream', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
        signal
      });
      if (!response.ok || !response.body) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || '全文阅读请求失败');
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let reportText = '';
      while (true) {
        const {value, done} = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          if (event.type === 'error') throw new Error(event.message || '生成失败');
          if (event.type === 'status' && $('streamStatus')) {
            $('streamStatus').textContent = event.message || '';
          }
          if (event.type === 'metadata') {
            const node = $('streamCoverage');
            if (event.mode === 'code') {
              if (node) node.innerHTML = `
                <strong>${Number(event.file_count || 0)}</strong>
                <span>项目文件</span>
                <span>已读取 ${Number(event.included_file_count || 0)} 个关键文件</span>
              `;
            } else {
              const coverage = event.coverage || {};
              if (node) node.innerHTML = `
                <strong>${coverage.covered_count || 0}/${coverage.total_count || 0}</strong>
                <span>章节证据已覆盖</span>
                <span>${Number(event.evidence_count || 0)} 条原文证据</span>
              `;
            }
            if (event.reading_state) {
              state.reading = event.reading_state;
              renderReadingState();
            }
          }
          if (event.type === 'delta') {
            reportText += event.text || '';
            requestAnimationFrame(() => finalizeStreamingReport(reportText));
            $('analysisOutput').scrollTop = $('analysisOutput').scrollHeight;
          }
          if (event.type === 'done') {
            $('streamCursor')?.remove();
            if ($('streamStatus')) {
              if (event.mode === 'code') {
                $('streamStatus').textContent = `解析完成，覆盖 ${Number(event.file_count || 0)} 个项目文件`;
              } else {
                const used = event.citation_check?.used_citations?.length || 0;
                $('streamStatus').textContent = used
                  ? `生成完成，已核对 ${used} 条本地引用`
                  : '生成完成，但未检测到有效本地引用';
              }
            }
            finalizeStreamingReport(reportText);
          }
        }
        if (done) break;
      }
      return reportText;
    };
    const streamArtifactExplanation = async (payload, onEvent, signal=null) => {
      const response = await fetch('/api/artifact-explain-stream', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
        signal
      });
      if (!response.ok || !response.body) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || t('图表解释请求失败', 'Artifact explanation request failed'));
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const {value, done} = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          if (event.type === 'error') {
            throw new Error(event.message || t('生成失败', 'Generation failed'));
          }
          onEvent(event);
        }
        if (done) break;
      }
    };
    const streamSelectionTranslation = async (text, onEvent) => {
      const response = await fetch('/api/translate-stream', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text})
      });
      if (!response.ok || !response.body) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || t('翻译请求失败', 'Translation request failed'));
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const {value, done} = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          if (event.type === 'error') {
            throw new Error(event.message || t('翻译失败', 'Translation failed'));
          }
          onEvent(event);
        }
        if (done) break;
      }
    };
    const closestElement = node => node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
    const normalizePdfSelectionText = value => String(value || '')
      .replace(/-\s*\n\s*(?=[a-z])/g, '')
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
    const selectedPdfRange = () => {
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
      const text = normalizePdfSelectionText(selection.toString());
      if (!text) return null;
      const range = selection.getRangeAt(0);
      const start = closestElement(range.startContainer);
      const end = closestElement(range.endContainer);
      if (!start?.closest('.pdf-text-layer') || !end?.closest('.pdf-text-layer')) return null;
      const page = start.closest('.pdf-page');
      if (!page) return null;
      const pageRect = page.getBoundingClientRect();
      const rects = [...range.getClientRects()].filter(rect =>
        rect.width > 1 && rect.height > 1
        && rect.bottom >= pageRect.top && rect.top <= pageRect.bottom
      );
      if (!rects.length) return null;
      return {selection, text, page, pageRect, rects};
    };
    const translatePdfSelection = async selected => {
      const {selection, text, page, pageRect, rects} = selected;
      const left = Math.min(...rects.map(rect => rect.left)) - pageRect.left;
      const right = Math.max(...rects.map(rect => rect.right)) - pageRect.left;
      const top = Math.min(...rects.map(rect => rect.top)) - pageRect.top;
      const desiredWidth = Math.max(300, right - left);
      const width = Math.min(pageRect.width - 16, desiredWidth);
      const clampedLeft = Math.max(8, Math.min(pageRect.width - width - 8, left));
      const overlay = document.createElement('section');
      overlay.className = 'pdf-translation';
      overlay.style.left = `${clampedLeft}px`;
      overlay.style.top = `${Math.max(8, top)}px`;
      overlay.style.width = `${width}px`;
      overlay.innerHTML = `
        <div class="pdf-translation-head">
          <span>${t('译文', 'Translation')}</span>
          <button class="icon-btn restore-translation" title="${t('还原原文', 'Restore original')}">↩</button>
        </div>
        <div class="pdf-translation-body">${t('正在翻译...', 'Translating...')}<span class="pdf-translation-cursor"></span></div>
      `;
      page.appendChild(overlay);
      selection.removeAllRanges();
      overlay.querySelector('.restore-translation').onclick = () => overlay.remove();
      const body = overlay.querySelector('.pdf-translation-body');
      let translated = '';
      try {
        await streamSelectionTranslation(text, event => {
          if (!overlay.isConnected) return;
          if (event.type === 'delta') {
            translated += event.text || '';
            body.textContent = translated;
            body.appendChild(Object.assign(document.createElement('span'), {className: 'pdf-translation-cursor'}));
            body.scrollTop = body.scrollHeight;
          }
          if (event.type === 'done') {
            body.innerHTML = formatMarkdown(translated || t('没有返回译文', 'No translation was returned'));
            renderMathInNode(body);
          }
        });
      } catch (error) {
        if (overlay.isConnected) {
          body.textContent = `${t('翻译失败', 'Translation failed')}: ${error.message}`;
        }
      }
    };
    document.addEventListener('keydown', event => {
      if (event.repeat || event.altKey || !(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'c') return;
      const selected = selectedPdfRange();
      if (!selected) {
        state.lastPdfCopyAt = 0;
        state.lastPdfCopyText = '';
        return;
      }
      const now = Date.now();
      const isSecondCopy = state.lastPdfCopyText === selected.text && now - state.lastPdfCopyAt <= 900;
      state.lastPdfCopyAt = now;
      state.lastPdfCopyText = selected.text;
      if (!isSecondCopy) return;
      event.preventDefault();
      state.lastPdfCopyAt = 0;
      state.lastPdfCopyText = '';
      translatePdfSelection(selected);
    });
    document.addEventListener('copy', event => {
      const selected = selectedPdfRange();
      if (!selected || !event.clipboardData) return;
      event.clipboardData.setData('text/plain', selected.text);
      event.preventDefault();
    });
    const renderSearch = payload => {
      $('searchResults').innerHTML = searchResultsMarkup(payload);
    };
    const searchResultsMarkup = payload => {
      const results = payload.results || [];
      return `
        <h2 class="output-title">检索结果</h2>
        ${payload.intent ? `<div class="search-intent"><strong>问题理解</strong><span>${escapeHtml(payload.intent)}</span></div>` : ''}
        ${(results || []).map(item => `
          <article class="result">
            <div class="result-title">
              ${escapeHtml(item.section || item.title || '')}
              ${item.page ? `<span class="tag">第 ${Number(item.page)} 页</span>` : ''}
            </div>
            <p>${renderHighlightedEvidence(item.snippet || '', item.highlights || [])}</p>
            ${item.relevance_reason ? `<div class="result-reason">匹配依据：${escapeHtml(item.relevance_reason)}</div>` : ''}
            <div class="citation">${escapeHtml(item.citation || '')}</div>
          </article>
        `).join('') || '<div class="muted">没有找到相关证据</div>'}
      `;
    };
    const renderHighlightedEvidence = (text, highlights) => {
      const source = String(text || '');
      const sourceLower = source.toLocaleLowerCase();
      const ranges = (highlights || []).map(value => {
        const sentence = String(value || '').trim();
        const start = sourceLower.indexOf(sentence.toLocaleLowerCase());
        return {start, end: start + sentence.length};
      }).filter(range => range.start >= 0)
        .sort((left, right) => left.start - right.start)
        .filter((range, index, all) => index === 0 || range.start >= all[index - 1].end);
      if (!ranges.length) return escapeHtml(source);
      let cursor = 0;
      let html = '';
      ranges.forEach(range => {
        html += escapeHtml(source.slice(cursor, range.start));
        html += `<strong class="evidence-highlight">${escapeHtml(source.slice(range.start, range.end))}</strong>`;
        cursor = range.end;
      });
      return html + escapeHtml(source.slice(cursor));
    };
    const loadArtifacts = async (forceRefresh=false) => {
      state.artifacts = [];
      renderArtifacts();
      if (!state.selected || state.selected.document_type !== 'paper') return;
      const data = await get(`/api/artifacts?id=${encodeURIComponent(state.selected.id)}${forceRefresh ? '&refresh=1' : ''}`);
      state.artifacts = data.artifacts || [];
      renderArtifacts();
    };
    const renderArtifacts = () => {
      $('artifactCount').textContent = state.artifacts.length;
      $('artifactList').innerHTML = state.artifacts.map(artifact => `
        <button class="artifact-item" data-artifact-id="${escapeHtml(artifact.artifact_id)}">
          ${artifact.image_available ? `
            <img class="artifact-thumb"
              src="/api/artifact-image?id=${encodeURIComponent(state.selected.id)}&artifact_id=${encodeURIComponent(artifact.artifact_id)}&v=${encodeURIComponent(artifact.imageVersion || '')}"
              alt="${escapeHtml(artifact.caption || '论文图表')}">
          ` : '<span class="artifact-thumb"></span>'}
          <span class="artifact-item-copy">
            <strong>${escapeHtml(artifactLabel(artifact))} · 第 ${escapeHtml(artifact.page || '?')} 页</strong>
            <span>${escapeHtml(artifact.caption || artifact.text || '')}</span>
          </span>
        </button>
      `).join('') || '<div class="muted">当前论文没有识别到图表</div>';
      document.querySelectorAll('.artifact-item').forEach(button => {
        button.onclick = () => openArtifact(button.dataset.artifactId);
      });
    };
    const closeArtifactWindow = () => {
      state.activeArtifactAbort?.abort();
      state.activeArtifactAbort = null;
      state.activeArtifactCleanup?.();
      state.activeArtifactCleanup = null;
      state.activeArtifactWindow?.remove();
      state.activeArtifactWindow = null;
    };
    const openArtifact = async artifactId => {
      const artifact = state.artifacts.find(item => item.artifact_id === artifactId);
      if (!artifact) return;
      if (
        state.activeArtifactWindow?.isConnected
        && state.activeArtifactWindow.dataset.artifactId === artifactId
      ) {
        state.activeArtifactWindow.style.zIndex = String(100 + state.windowIndex++);
        return;
      }
      closeArtifactWindow();
      const index = state.windowIndex++;
      const windowNode = document.createElement('section');
      windowNode.className = 'artifact-window';
      windowNode.dataset.artifactId = artifactId;
      windowNode.style.width = 'min(760px, calc(100vw - 40px))';
      windowNode.style.height = 'min(820px, calc(100vh - 70px))';
      windowNode.style.left = `${Math.min(window.innerWidth - 380, 280 + (index % 5) * 38)}px`;
      windowNode.style.top = '62px';
      windowNode.style.zIndex = String(50 + index);
      const pageUrl = artifact.image_available
        ? `/api/artifact-page-image?id=${encodeURIComponent(state.selected.id)}&page=${encodeURIComponent(artifact.page)}`
        : '';
      windowNode.innerHTML = `
        <div class="artifact-window-head">
          <strong>${escapeHtml(artifact.caption || artifact.text || '论文图表')}</strong>
          <button class="btn primary save-crop" title="保存当前裁剪区域">保存裁剪</button>
          <button class="btn add-artifact-note" disabled>${t('添加到纪要', 'Add to Digest')}</button>
          <button class="btn regenerate-artifact">${t('重新生成', 'Regenerate')}</button>
          <button class="icon-btn close-artifact" title="关闭">×</button>
        </div>
        <div class="artifact-window-body">
          ${pageUrl ? `
            <div class="crop-stage">
              <img src="${pageUrl}" alt="论文第 ${escapeHtml(artifact.page)} 页">
              <div class="crop-selection">
                ${['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'].map(handle =>
                  `<span class="crop-handle" data-handle="${handle}"></span>`
                ).join('')}
              </div>
            </div>
            <div class="crop-help">拖动图像调整位置，拖动边角扩大或缩小当前范围。</div>
          ` : '<div class="muted">该资料没有可裁剪的 PDF 图像。</div>'}
          <div class="artifact-explanation">${artifact.interpretation?.interpretation
            ? formatMarkdown(artifact.interpretation.interpretation)
            : t('正在解释图表...', 'Analyzing artifact...')}</div>
        </div>
      `;
      $('floatingLayer').appendChild(windowNode);
      state.activeArtifactWindow = windowNode;
      state.activeArtifactAbort = new AbortController();
      windowNode.querySelector('.close-artifact').onclick = closeArtifactWindow;
      makeDraggable(windowNode, windowNode.querySelector('.artifact-window-head'));
      const stage = windowNode.querySelector('.crop-stage');
      const saveButton = windowNode.querySelector('.save-crop');
      const noteButton = windowNode.querySelector('.add-artifact-note');
      if (!stage || !saveButton) return;
      const image = stage.querySelector('img');
      const selection = stage.querySelector('.crop-selection');
      let bbox = artifact.region?.bbox ? [...artifact.region.bbox] : [0.05, 0.05, 0.95, 0.95];
      let dirty = false;
      const renderViewport = () => {
        if (!image.naturalWidth || !image.naturalHeight) return;
        const bodyWidth = windowNode.querySelector('.artifact-window-body').clientWidth - 24;
        const maxWidth = Math.max(240, bodyWidth);
        const maxHeight = Math.max(180, Math.min(570, window.innerHeight - 240));
        const bboxWidth = Math.max(0.025, bbox[2] - bbox[0]);
        const bboxHeight = Math.max(0.025, bbox[3] - bbox[1]);
        const cropAspect = (bboxWidth * image.naturalWidth) / (bboxHeight * image.naturalHeight);
        const viewportWidth = Math.min(maxWidth, maxHeight * cropAspect);
        const viewportHeight = viewportWidth / cropAspect;
        const fullWidth = viewportWidth / bboxWidth;
        const fullHeight = viewportHeight / bboxHeight;
        stage.style.width = `${viewportWidth}px`;
        stage.style.height = `${viewportHeight}px`;
        image.style.width = `${fullWidth}px`;
        image.style.height = `${fullHeight}px`;
        image.style.left = `${-bbox[0] * fullWidth}px`;
        image.style.top = `${-bbox[1] * fullHeight}px`;
      };
      image.onload = renderViewport;
      renderViewport();
      selection.onpointerdown = event => {
        event.stopPropagation();
        const original = [...bbox];
        const handle = event.target.closest('.crop-handle')?.dataset.handle || 'move';
        const startClientX = event.clientX;
        const startClientY = event.clientY;
        const stageRect = stage.getBoundingClientRect();
        const originalWidth = original[2] - original[0];
        const originalHeight = original[3] - original[1];
        const fullPageWidth = stageRect.width / originalWidth;
        const fullPageHeight = stageRect.height / originalHeight;
        const captureTarget = event.target;
        captureTarget.setPointerCapture(event.pointerId);
        captureTarget.onpointermove = move => {
          const deltaX = (move.clientX - startClientX) / fullPageWidth;
          const deltaY = (move.clientY - startClientY) / fullPageHeight;
          if (handle === 'move') {
            const left = Math.max(0, Math.min(1 - originalWidth, original[0] - deltaX));
            const top = Math.max(0, Math.min(1 - originalHeight, original[1] - deltaY));
            bbox = [left, top, left + originalWidth, top + originalHeight];
          } else {
            const minimum = 0.025;
            let [left, top, right, bottom] = original;
            if (handle.includes('w')) left = Math.max(0, Math.min(original[0] + deltaX, right - minimum));
            if (handle.includes('e')) right = Math.min(1, Math.max(original[2] + deltaX, left + minimum));
            if (handle.includes('n')) top = Math.max(0, Math.min(original[1] + deltaY, bottom - minimum));
            if (handle.includes('s')) bottom = Math.min(1, Math.max(original[3] + deltaY, top + minimum));
            bbox = [left, top, right, bottom];
          }
          dirty = true;
          renderViewport();
        };
        captureTarget.onpointerup = () => { captureTarget.onpointermove = null; };
      };
      const resizeObserver = new ResizeObserver(renderViewport);
      resizeObserver.observe(windowNode.querySelector('.artifact-window-body'));
      state.activeArtifactCleanup = () => resizeObserver.disconnect();
      saveButton.onclick = async () => {
        if (!dirty) return notify('裁剪区域没有变化');
        try {
          const data = await api('/api/artifact-region', {
            document_id: state.selected.id,
            artifact_id: artifact.artifact_id,
            bbox
          });
          artifact.region = data.region;
          artifact.imageVersion = Date.now();
          dirty = false;
          renderArtifacts();
          notify('裁剪区域已保存');
        } catch (error) { notify(error.message, true); }
      };
      const refreshArtifactNoteButton = () => {
        const interpretation = artifact.interpretation?.interpretation || '';
        const recorded = state.readingHistory.some(entry =>
          entry.kind === 'artifact_explanation'
          && entry.metadata?.artifact_id === artifact.artifact_id
          && String(entry.answer || '').trim() === String(interpretation).trim()
        );
        noteButton.disabled = !interpretation || recorded;
        noteButton.textContent = recorded
          ? t('已添加到纪要', 'Added to Digest')
          : t('添加到纪要', 'Add to Digest');
      };
      noteButton.onclick = async () => {
        try {
          noteButton.disabled = true;
          const data = await api('/api/artifact-note', {
            document_id: state.selected.id,
            artifact_id: artifact.artifact_id
          });
          state.reading = data.state;
          await loadReadingHistory();
          refreshArtifactNoteButton();
          notify(data.added
            ? t('图表解释已添加到阅读纪要', 'Artifact explanation added to the digest')
            : t('该版本解释已在阅读纪要中', 'This explanation is already in the digest'));
        } catch (error) {
          noteButton.disabled = false;
          notify(error.message, true);
        }
      };
      const generateArtifactExplanation = async regenerate => {
        try {
        const explanationNode = windowNode.querySelector('.artifact-explanation');
        let explanationText = '';
        let renderQueued = false;
        const renderExplanation = () => {
          renderQueued = false;
          explanationNode.innerHTML = formatMarkdown(explanationText);
          highlightCode(explanationNode);
          renderMathInNode(explanationNode);
          explanationNode.scrollTop = explanationNode.scrollHeight;
        };
        await streamArtifactExplanation({
          document_id: state.selected.id,
          artifact_id: artifact.artifact_id,
          regenerate
        }, event => {
          if (!windowNode.isConnected) return;
          if (event.type === 'status' && !explanationText) {
            explanationNode.textContent = event.message || t('正在解释图表...', 'Analyzing artifact...');
          }
          if (event.type === 'delta') {
            explanationText += event.text || '';
            if (!renderQueued) {
              renderQueued = true;
              requestAnimationFrame(renderExplanation);
            }
          }
          if (event.type === 'done') {
            artifact.interpretation = event.interpretation;
            explanationText = explanationText
              || event.interpretation?.interpretation
              || t('没有生成解释。', 'No explanation was generated.');
            renderExplanation();
            refreshArtifactNoteButton();
          }
        }, state.activeArtifactAbort?.signal);
      } catch (error) {
        if (error.name === 'AbortError' || !windowNode.isConnected) return;
        windowNode.querySelector('.artifact-explanation').textContent =
          `${t('解释失败', 'Explanation failed')}: ${error.message}`;
      }
      };
      windowNode.querySelector('.regenerate-artifact').onclick = () => generateArtifactExplanation(true);
      if (artifact.interpretation?.interpretation) {
        renderMathInNode(windowNode.querySelector('.artifact-explanation'));
        refreshArtifactNoteButton();
      } else {
        generateArtifactExplanation(false);
      }
    };
    const makeDraggable = (node, handle) => {
      handle.onpointerdown = event => {
        if (event.target.closest('button')) return;
        const rect = node.getBoundingClientRect();
        const offsetX = event.clientX - rect.left;
        const offsetY = event.clientY - rect.top;
        node.style.zIndex = String(100 + state.windowIndex++);
        handle.setPointerCapture(event.pointerId);
        handle.onpointermove = move => {
          node.style.left = `${Math.max(0, Math.min(window.innerWidth - 120, move.clientX - offsetX))}px`;
          node.style.top = `${Math.max(52, Math.min(window.innerHeight - 60, move.clientY - offsetY))}px`;
        };
        handle.onpointerup = () => { handle.onpointermove = null; };
      };
    };
    const renderComparison = payload => {
      const data = payload.data || payload;
      const local = data.local_evidence || [];
      const related = data.related_papers || [];
      $('analysisOutput').innerHTML = `
        <h2 class="output-title">创新与相关工作对比</h2>
        <article class="section-block">
          <div class="section-heading"><h3>本地论文证据</h3><span class="tag">${local.length}</span></div>
          ${local.map(item => `<div class="evidence">${escapeHtml(item.snippet || '')}<div class="citation">${escapeHtml(item.citation || '')}</div></div>`).join('') || '<div class="muted">未找到本地证据</div>'}
        </article>
        <article class="section-block">
          <div class="section-heading"><h3>相关论文</h3><span class="tag">${related.length}</span></div>
          ${related.map(item => `<div class="result"><strong>${escapeHtml(item.title || '')}</strong><p>${escapeHtml(item.summary || item.abstract || '')}</p><div class="citation">${escapeHtml(item.citation || item.url || '')}</div></div>`).join('') || '<div class="muted">没有相关论文结果</div>'}
        </article>
      `;
    };
    const formatMessageText = value => {
      const math = tokenizeMath(value);
      const escaped = escapeHtml(math.text);
      const withCode = escaped.replace(/`([^`\n]+)`/g, '<code>$1</code>');
      const withStrong = withCode.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
      const html = withStrong.split(/\n{2,}/).map(block =>
        `<p>${block.replace(/\n/g, '<br>')}</p>`
      ).join('');
      return math.restore(html);
    };
    const renderMathInNode = node => {
      if (typeof window.renderMathInElement !== 'function') return;
      window.renderMathInElement(node, {
        delimiters: [
          {left: '$$', right: '$$', display: true},
          {left: '\\[', right: '\\]', display: true},
          {left: '\\(', right: '\\)', display: false},
          {left: '$', right: '$', display: false}
        ],
        throwOnError: false
      });
    };
    const renderMessageMath = () => {
      document.querySelectorAll('.message.assistant .message-content').forEach(renderMathInNode);
    };
    const renderMessages = () => {
      $('messages').classList.toggle('visible', state.messages.length > 0);
      $('messages').innerHTML = state.messages.map(message => `
        <div class="message ${message.role}">
          <div class="message-content">${formatMessageText(message.text)}</div>
        </div>
      `).join('');
      renderMessageMath();
      $('messages').scrollTop = $('messages').scrollHeight;
    };
    $('modeTabs').onclick = event => {
      const tab = event.target.closest('.mode-tab');
      if (tab) setMode(tab.dataset.mode);
    };
    $('inspectorTabs').onclick = event => {
      const tab = event.target.closest('.inspector-tab');
      if (!tab) return;
      document.querySelectorAll('.inspector-tab').forEach(item => item.classList.toggle('active', item === tab));
      document.querySelectorAll('.inspector-panel').forEach(panel =>
        panel.classList.toggle('active', panel.id === `inspector-${tab.dataset.inspectorPanel}`)
      );
    };
    $('previousPage').onclick = () => jumpToPage((state.currentPage || 1) - 1);
    $('nextPage').onclick = () => jumpToPage((state.currentPage || 1) + 1);
    $('pageJump').onchange = event => jumpToPage(event.target.value);
    $('pageJump').onkeydown = event => {
      if (event.key === 'Enter') {
        event.preventDefault();
        jumpToPage(event.target.value);
      }
    };
    window.addEventListener('resize', () => {
      document.querySelectorAll('.pdf-text-layer').forEach(layoutPdfTextLayer);
    });
    $('markdownEditMode').onclick = () => setMarkdownMode('edit');
    $('markdownPreviewMode').onclick = () => setMarkdownMode('preview');
    $('markdownEditor').oninput = () => {
      state.markdownDirty = true;
      $('markdownSaveState').textContent = '未保存';
    };
    $('saveMarkdown').onclick = () => withBusy($('saveMarkdown'), '保存中...', async () => {
      try {
        const data = await api('/api/document-save', {
          document_id: state.selected.id,
          content: $('markdownEditor').value
        });
        state.selected = data.document;
        state.docs = state.docs.map(doc => doc.id === data.document.id ? data.document : doc);
        state.markdownDirty = false;
        $('markdownSaveState').textContent = '已保存';
        renderDocs();
        renderSelected();
        if (!$('markdownPreview').hidden) $('markdownPreview').innerHTML = formatMarkdown(data.content);
      } catch (error) {
        $('markdownSaveState').textContent = '保存失败';
        notify(error.message, true);
      }
    });
    $('addTimelineNote').onclick = () => {
      $('timelineNoteComposer').hidden = false;
      $('timelineNoteText').focus();
    };
    $('cancelTimelineNote').onclick = () => {
      $('timelineNoteComposer').hidden = true;
      $('timelineNoteText').value = '';
    };
    $('saveTimelineNote').onclick = () => withBusy($('saveTimelineNote'), t('添加中...', 'Adding...'), async () => {
      const text = $('timelineNoteText').value.trim();
      if (!text) return;
      try {
        const data = await api('/api/note', {...requireDoc(), kind: 'note', text});
        state.reading = data.state;
        $('timelineNoteComposer').hidden = true;
        $('timelineNoteText').value = '';
        await loadReadingHistory();
      } catch (error) { notify(error.message, true); }
    });
    $('summarizeTimeline').onclick = () => withBusy($('summarizeTimeline'), t('总结中...', 'Summarizing...'), async () => {
      try {
        const data = await api('/api/timeline-summary', requireDoc());
        state.reading = data.state;
        await loadReadingHistory();
        openReadingHistory(state.readingHistory.length - 1);
      } catch (error) { notify(error.message, true); }
    });
    $('codeDetailMode').onclick = event => {
      const button = event.target.closest('[data-code-detail]');
      if (!button) return;
      state.codeDetail = button.dataset.codeDetail;
      document.querySelectorAll('[data-code-detail]').forEach(item => item.classList.toggle('active', item === button));
    };
    $('editCodeMarkdown').onclick = async () => {
      const file = state.codeFileCache.get(state.activeCodeId);
      if (!file?.editable) return;
      if (!state.codeMarkdownEditing) {
        state.codeMarkdownEditing = true;
        $('editCodeMarkdown').textContent = '预览';
        $('saveCodeMarkdown').hidden = false;
        $('codeContent').innerHTML = `<textarea class="markdown-editor" id="codeMarkdownEditor" spellcheck="false">${escapeHtml(file.draft ?? file.content ?? '')}</textarea>`;
        $('codeMarkdownEditor').focus();
      } else {
        file.draft = $('codeMarkdownEditor')?.value ?? file.draft ?? file.content ?? '';
        state.codeMarkdownEditing = false;
        $('editCodeMarkdown').textContent = '编辑 Markdown';
        $('codeContent').innerHTML = `<div class="markdown-preview">${formatMarkdown(file.draft)}</div>`;
        highlightCode($('codeContent'));
        renderMathInNode($('codeContent'));
      }
    };
    $('saveCodeMarkdown').onclick = () => withBusy($('saveCodeMarkdown'), '保存中...', async () => {
      const file = state.codeFileCache.get(state.activeCodeId);
      if (!file?.editable) return;
      const content = $('codeMarkdownEditor')?.value ?? file.draft ?? file.content ?? '';
      try {
        await api('/api/document-save', {document_id: file.id, content});
        file.content = content;
        file.draft = content;
        notify('Markdown 已保存');
      } catch (error) {
        notify(error.message, true);
      }
    });
    $('fieldFilter').oninput = renderDocs;
    $('libraryView').onchange = renderDocs;
    $('categoryFilter').onchange = renderDocs;
    $('refreshDocs').onclick = () => loadDocs().then(() => notify('资料库已刷新')).catch(error => notify(error.message, true));
    $('openImport').onclick = () => $('importModal').classList.add('open');
    $('closeImport').onclick = $('cancelImport').onclick = () => $('importModal').classList.remove('open');
    $('importModal').onclick = event => {
      if (event.target === $('importModal')) $('importModal').classList.remove('open');
    };
    const closeCategoryModal = () => {
      $('categoryModal').classList.remove('open');
      state.categoryTargetId = null;
    };
    $('closeCategory').onclick = $('cancelCategory').onclick = closeCategoryModal;
    $('categoryModal').onclick = event => {
      if (event.target === $('categoryModal')) closeCategoryModal();
    };
    $('saveCategory').onclick = () => withBusy($('saveCategory'), '保存中...', async () => {
      if (!state.categoryTargetId) return;
      try {
        await updateDocumentOrganization(
          state.categoryTargetId,
          {category: $('categoryName').value.trim()},
          '分类已更新'
        );
        closeCategoryModal();
      } catch (error) {
        notify(error.message, true);
      }
    });
    $('categoryName').onkeydown = event => {
      if (event.key === 'Enter') {
        event.preventDefault();
        $('saveCategory').click();
      }
    };
    const updateImportMode = () => {
      const isCode = state.ingestType === 'code';
      const paperAccept = '.pdf,.txt,.md,.markdown,.rst';
      const codeAccept = '.ipynb,.md,.markdown,.txt,.rst,.py,.js,.jsx,.ts,.tsx,.java,.c,.h,.cpp,.hpp,.cs,.go,.rs,.rb,.php,.swift,.kt,.kts,.scala,.sh,.ps1,.sql,.html,.css,.json,.yaml,.yml,.toml,.xml';
      $('ingestFile').accept = isCode ? codeAccept : paperAccept;
      $('folderPicker').hidden = !isCode;
      $('importPickers').classList.toggle('code-mode', isCode);
      $('filePickerHint').textContent = isCode
        ? '支持 .ipynb 和常见代码文件，可多选'
        : '支持 PDF、Markdown 和文本文件';
      if (!isCode) {
        $('ingestFolder').value = '';
        $('folderPickerTitle').textContent = '选择代码文件夹';
        $('folderPickerHint').textContent = '保留目录结构，只导入支持的文本代码文件';
      }
    };
    $('typePicker').onclick = event => {
      const option = event.target.closest('.type-option');
      if (!option) return;
      state.ingestType = option.dataset.type;
      document.querySelectorAll('.type-option').forEach(item => item.classList.toggle('active', item === option));
      updateImportMode();
    };
    $('ingestFile').onchange = () => {
      const files = [...$('ingestFile').files];
      if (files.some(file => fileSuffix(file.name) === '.ipynb') && state.ingestType !== 'code') {
        state.ingestType = 'code';
        document.querySelectorAll('.type-option').forEach(item =>
          item.classList.toggle('active', item.dataset.type === 'code')
        );
        updateImportMode();
      }
      if (files.length) $('ingestFolder').value = '';
      $('filePickerTitle').textContent = files.length > 1 ? `已选择 ${files.length} 个文件` : (files[0]?.name || '点击选择文件');
      $('filePickerHint').textContent = files.length
        ? `${(files.reduce((sum, file) => sum + file.size, 0) / 1024 / 1024).toFixed(2)} MB`
        : (state.ingestType === 'code' ? '支持 .ipynb 和常见代码文件，可多选' : '支持 PDF、Markdown 和文本文件');
    };
    $('ingestFolder').onchange = () => {
      const files = [...$('ingestFolder').files];
      if (files.length) {
        $('ingestFile').value = '';
        $('filePickerTitle').textContent = '点击选择文件';
      }
      const root = files[0]?.webkitRelativePath?.split('/')[0] || '';
      $('folderPickerTitle').textContent = root || '选择代码文件夹';
      $('folderPickerHint').textContent = files.length ? `${files.length} 个文件，将跳过依赖目录、大文件并最多导入 500 个` : '保留目录结构，只导入支持的文本代码文件';
    };
    const paperUploadSuffixes = new Set(['.pdf', '.txt', '.md', '.markdown', '.rst']);
    const codeUploadSuffixes = new Set([
      '.txt', '.md', '.markdown', '.rst', '.ipynb', '.py', '.js', '.jsx',
      '.ts', '.tsx', '.java', '.c', '.h', '.cpp', '.hpp', '.cs', '.go', '.rs',
      '.rb', '.php', '.swift', '.kt', '.kts', '.scala', '.sh', '.ps1', '.sql',
      '.html', '.css', '.json', '.yaml', '.yml', '.toml', '.xml'
    ]);
    const fileSuffix = name => {
      const index = String(name).lastIndexOf('.');
      return index >= 0 ? String(name).slice(index).toLowerCase() : '';
    };
    const ignoredCodeDirectories = new Set([
      '.git', '.idea', '.vscode', '.venv', 'venv', 'env', 'node_modules',
      '__pycache__', 'dist', 'build', '.next', 'coverage', 'target', 'vendor'
    ]);
    const allowedFolderFile = file => {
      const path = String(file.webkitRelativePath || file.name).replace(/\\/g, '/');
      const parts = path.split('/');
      return codeUploadSuffixes.has(fileSuffix(file.name))
        && !parts.some(part => ignoredCodeDirectories.has(part))
        && file.size <= 5 * 1024 * 1024;
    };
    const uploadMaterial = async ({file, source, category}) => {
      const params = new URLSearchParams({
        filename: file.name,
        document_type: state.ingestType,
        field: state.ingestType === 'code' ? '代码' : '论文',
        title: file.name.replace(/\.[^.]+$/, ''),
        source: source || file.name
      });
      if (category) params.set('category', category);
      const response = await fetch(`/api/upload?${params}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/octet-stream'},
        body: file
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `导入 ${file.name} 失败`);
      return data.document;
    };
    $('ingestBtn').onclick = () => withBusy($('ingestBtn'), '导入中...', async () => {
      try {
        const folderFiles = [...$('ingestFolder').files];
        const selectedFiles = folderFiles.length ? folderFiles : [...$('ingestFile').files];
        const files = folderFiles.length
          ? selectedFiles.filter(allowedFolderFile).slice(0, 500)
          : selectedFiles.filter(file => {
              const allowedSuffixes = state.ingestType === 'code' ? codeUploadSuffixes : paperUploadSuffixes;
              return allowedSuffixes.has(fileSuffix(file.name)) && file.size <= 100 * 1024 * 1024;
            });
        const skippedBeforeUpload = selectedFiles.length - files.length;
        if (!files.length) throw new Error('请选择支持的文件或代码文件夹');
        const root = folderFiles[0]?.webkitRelativePath?.split('/')[0] || '';
        const imported = [];
        const failures = [];
        for (let index = 0; index < files.length; index += 1) {
          const file = files[index];
          $('ingestBtn').textContent = `导入 ${index + 1}/${files.length}`;
          const relative = file.webkitRelativePath || file.name;
          const source = root && relative.startsWith(`${root}/`) ? relative.slice(root.length + 1) : relative;
          try {
            imported.push(await uploadMaterial({
              file,
              source,
              category: root || ''
            }));
          } catch (error) {
            failures.push(`${file.name}: ${error.message}`);
          }
          if (index % 5 === 4) await new Promise(resolve => requestAnimationFrame(resolve));
        }
        if (!imported.length) throw new Error(failures[0] || '没有文件导入成功');
        $('importModal').classList.remove('open');
        await loadDocs();
        await selectDocument(imported[0].id);
        $('ingestFile').value = '';
        $('ingestFolder').value = '';
        $('filePickerTitle').textContent = '点击选择文件';
        $('folderPickerTitle').textContent = '选择代码文件夹';
        updateImportMode();
        const skipped = skippedBeforeUpload + failures.length;
        notify(skipped ? `已导入 ${imported.length} 个，跳过 ${skipped} 个` : `已导入 ${imported.length} 个资料`);
      } catch (error) { notify(error.message, true); }
    });
    $('removeBtn').onclick = () => {
      if (!state.selected) return;
      removeDocument(state.selected.id).catch(error => notify(error.message, true));
    };
    const runPrimaryAnalysis = (regenerate=false) => withBusy(
      regenerate ? $('regenerateAnalysis') : $('readBtn'),
      state.selected?.document_type === 'code' ? '解析中...' : '阅读中...',
      async () => {
      const active = {type: 'stream', controller: new AbortController()};
      try {
        if (state.activeLongTask) throw new Error(t('已有长任务正在执行', 'Another long task is running'));
        state.activeLongTask = active;
        showLongTask(
          state.selected?.document_type === 'code' ? t('正在解析代码', 'Analyzing code') : t('正在阅读全文', 'Reading full paper'),
          t('模型正在流式生成', 'Streaming model output'),
          35
        );
        beginStreamingAnalysis();
        await streamRead({
          ...requireDoc(),
          related_limit: 0,
          regenerate,
          code_detail: state.codeDetail
        }, active.controller.signal);
        await loadReadingHistory();
        notify(state.selected?.document_type === 'code' ? '代码解析完成' : '全文阅读完成');
      } catch (error) {
        notify(error.name === 'AbortError' ? t('任务已取消', 'Task cancelled') : error.message, error.name !== 'AbortError');
      } finally {
        hideLongTask(active);
      }
      }
    );
    $('readBtn').onclick = () => runPrimaryAnalysis(false);
    $('regenerateAnalysis').onclick = () => runPrimaryAnalysis(true);
    $('compareBtn').onclick = () => withBusy($('compareBtn'), '对比中...', async () => {
      try {
        const data = await api('/api/compare', {
          ...requireDoc(),
          topic: $('compareTopic').value.trim() || state.selected.title,
          related_limit: 5
        });
        renderComparison(data);
        notify('对比完成');
      } catch (error) { notify(error.message, true); }
    });
    $('searchBtn').onclick = () => withBusy($('searchBtn'), '检索中...', async () => {
      try {
        const data = await api('/api/search', {
          ...requireDoc(),
          query: $('searchQuery').value,
          limit: 10
        });
        renderSearch(data);
        await loadReadingHistory();
        notify(`找到 ${(data.results || []).length} 条证据`);
      } catch (error) { notify(error.message, true); }
    });
    $('searchQuery').onkeydown = event => {
      if (event.key === 'Enter') $('searchBtn').click();
    };
    const sendChat = () => withBusy($('chatBtn'), '…', async () => {
      const question = $('chatQuestion').value.trim();
      if (!question) return;
      state.messages.push({role: 'user', text: question});
      const assistantMessage = {role: 'assistant', text: ''};
      state.messages.push(assistantMessage);
      $('chatQuestion').value = '';
      renderMessages();
      try {
        const response = await fetch('/api/chat-stream', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            ...(state.selected ? requireDoc() : {}),
            question,
            conversation_id: state.selected ? `paper-${state.selected.id}` : 'paper-agent-ui'
          })
        });
        if (!response.ok || !response.body) {
          const error = await response.json().catch(() => ({}));
          throw new Error(error.error || '提问请求失败');
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let renderQueued = false;
        const queueChatRender = () => {
          if (renderQueued) return;
          renderQueued = true;
          requestAnimationFrame(() => {
            renderQueued = false;
            renderMessages();
          });
        };
        while (true) {
          const {value, done} = await reader.read();
          buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (!line.trim()) continue;
            const event = JSON.parse(line);
            if (event.type === 'error') throw new Error(event.message || '提问失败');
            if (event.type === 'delta') {
              assistantMessage.text += event.text || '';
              queueChatRender();
            }
            if (event.type === 'done') {
              assistantMessage.text = event.answer || assistantMessage.text || '没有返回回答';
              if (event.reading_state) {
                state.reading = event.reading_state;
                renderReadingState();
              }
              await loadReadingHistory();
              renderMessages();
            }
          }
          if (done) break;
        }
      } catch (error) {
        assistantMessage.text = `请求失败：${error.message}`;
        renderMessages();
      }
    });
    $('chatBtn').onclick = sendChat;
    $('chatQuestion').onkeydown = event => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendChat();
      }
    };
    const resetResearchTask = () => {
      clearTimeout(state.researchSaveTimer);
      state.researchTask = null;
      state.researchCandidates = [];
      state.researchAnalysis = null;
      state.researchCorrespondence = null;
      state.researchExperiment = null;
      state.researchAttachments = [];
      applyResearchTask(null);
    };
    const setWorkspace = workspace => {
      state.workspace = workspace;
      $('appShell').hidden = workspace !== 'reading';
      $('researchWorkspace').hidden = workspace !== 'research';
      $('openReading').classList.toggle('active', workspace === 'reading');
      $('openResearch').classList.toggle('active', workspace === 'research');
      $('topTitle').textContent = workspace === 'research'
        ? t('科研辅助工作台', 'Research Copilot Workspace')
        : t('论文阅读工作台', 'Paper Reading Workspace');
    };
    const createResearchTask = async name => {
      const data = await api('/api/research/new', {
        name,
        direction: '',
        paper_ids: [],
        code_ids: []
      });
      state.researchTask = data.task;
      state.researchTasks = [data.task, ...state.researchTasks.filter(item => item.id !== data.task.id)];
      applyResearchTask(data.task);
      return data.task;
    };
    const ensureResearchTask = async () => {
      if (!state.researchTask) throw new Error(t('请先新建并命名科研任务', 'Create and name a research task first'));
      return state.researchTask;
    };
    const persistResearchTask = async () => {
      clearTimeout(state.researchSaveTimer);
      if (!state.researchTask) return null;
      const data = await api('/api/research/update', {
        task_id: state.researchTask.id,
        name: $('researchTaskName').value.trim(),
        direction: $('researchDirection').value.trim(),
        paper_ids: selectedResearchPaperIds(),
        code_ids: selectedResearchCodeIds(),
        candidate_sort: $('researchCandidateSort').value || 'relevance'
      });
      const previousAnalysis = state.researchAnalysis;
      const previousCorrespondence = state.researchCorrespondence;
      const previousExperiment = state.researchExperiment;
      state.researchTask = data.task;
      state.researchTasks = [data.task, ...state.researchTasks.filter(item => item.id !== data.task.id)]
        .sort((left, right) => String(right.updated_at || '').localeCompare(String(left.updated_at || '')));
      state.researchAnalysis = data.task.analysis || null;
      state.researchCorrespondence = data.task.correspondence || null;
      state.researchExperiment = data.task.experiment || null;
      renderResearchTaskSelect();
      if (previousAnalysis && !state.researchAnalysis) renderResearchAnalysis();
      if (previousCorrespondence && !state.researchCorrespondence) renderResearchCorrespondence();
      if (previousExperiment && !state.researchExperiment) renderResearchExperiment();
      return data.task;
    };
    const scheduleResearchTaskSave = () => {
      clearTimeout(state.researchSaveTimer);
      if (!state.researchTask) return;
      state.researchSaveTimer = setTimeout(() => {
        persistResearchTask().catch(error => notify(error.message, true));
      }, 550);
    };
    $('openReading').onclick = () => setWorkspace('reading');
    $('openResearch').onclick = async () => {
      setWorkspace('research');
      try {
        await loadResearchTasks(!state.researchTask);
      } catch (error) {
        notify(error.message, true);
        resetResearchTask();
      }
    };
    const closeResearchTaskModal = () => $('researchTaskModal').classList.remove('open');
    $('newResearchTask').onclick = () => {
      $('newResearchTaskName').value = '';
      $('researchTaskModal').classList.add('open');
      setTimeout(() => $('newResearchTaskName').focus(), 0);
    };
    $('closeResearchTaskModal').onclick = $('cancelResearchTask').onclick = closeResearchTaskModal;
    $('researchTaskModal').onclick = event => {
      if (event.target === $('researchTaskModal')) closeResearchTaskModal();
    };
    $('confirmResearchTask').onclick = () => withBusy($('confirmResearchTask'), t('新建中...', 'Creating...'), async () => {
      try {
        const name = $('newResearchTaskName').value.trim();
        if (!name) throw new Error(t('请输入任务名称', 'Enter a task name'));
        await createResearchTask(name);
        closeResearchTaskModal();
        notify(t('已创建新的科研任务', 'New research task created'));
      } catch (error) { notify(error.message, true); }
    });
    $('newResearchTaskName').onkeydown = event => {
      if (event.key === 'Enter') $('confirmResearchTask').click();
    };
    $('researchTaskSelect').onchange = async () => {
      const taskId = $('researchTaskSelect').value;
      if (!taskId) {
        resetResearchTask();
        return;
      }
      try {
        const data = await get(`/api/research-task?id=${encodeURIComponent(taskId)}`);
        applyResearchTask(data.task);
      } catch (error) { notify(error.message, true); }
    };
    const discoverResearchPapers = async () => {
      await ensureResearchTask();
      await persistResearchTask();
      const data = await runBackgroundTask('research_discover', {
        task_id: state.researchTask.id,
        direction: $('researchDirection').value.trim(),
        paper_ids: selectedResearchPaperIds(),
        code_ids: selectedResearchCodeIds(),
        candidate_sort: $('researchCandidateSort').value || 'relevance',
        limit: 8
      }, t('正在寻找相关论文', 'Finding related papers'));
      state.researchTask = data.task;
      state.researchCandidates = data.candidates || [];
      state.researchAnalysis = null;
      state.researchExperiment = null;
      await loadResearchTasks(false);
      notify(state.researchCandidates.length
        ? `找到 ${state.researchCandidates.length} 篇候选论文`
        : '检索已完成，但没有找到匹配论文，请调整 Prompt');
    };
    const importResearchCandidate = async candidateId => {
      if (!state.researchTask) return;
      try {
        const data = await runBackgroundTask('research_import', {
          task_id: state.researchTask.id,
          candidate_id: candidateId
        }, t('正在下载并导入论文', 'Downloading and importing paper'));
        applyResearchTask(data.task);
        await loadDocs();
        await loadResearchTasks(false);
        notify(t('论文已导入资料库', 'Paper imported into the library'));
      } catch (error) {
        notify(error.name === 'AbortError' ? t('导入已取消', 'Import cancelled') : error.message, error.name !== 'AbortError');
      }
    };
    $('researchDiscover').onclick = () => withBusy($('researchDiscover'), '正在寻找...', async () => {
      try {
        await discoverResearchPapers();
      } catch (error) { notify(error.message, true); }
    });
    $('researchAppendDiscover').onclick = () => withBusy(
      $('researchAppendDiscover'),
      '正在追加并寻找...',
      async () => {
        try {
          const addition = $('researchPromptAppend').value.trim();
          if (!addition) throw new Error(t('请输入需要追加的检索要求', 'Enter a requirement to append'));
          const current = $('researchDirection').value.trim();
          $('researchDirection').value = current
            ? `${current}\n\n补充要求：\n${addition}`
            : `补充要求：\n${addition}`;
          $('researchPromptAppend').value = '';
          await discoverResearchPapers();
        } catch (error) { notify(error.message, true); }
      }
    );
    $('researchTaskName').oninput = scheduleResearchTaskSave;
    $('researchDirection').oninput = scheduleResearchTaskSave;
    const handleResearchMaterialChange = () => {
      $('researchCorrespondence').disabled = !state.researchTask
        || selectedResearchPaperIds().length === 0
        || selectedResearchCodeIds().length === 0;
      scheduleResearchTaskSave();
    };
    $('researchPaperChoices').onchange = handleResearchMaterialChange;
    $('researchCodeChoices').onchange = handleResearchMaterialChange;
    $('researchCandidateSort').onchange = () => {
      renderResearchCandidates();
      scheduleResearchTaskSave();
    };
    $('researchAnalyze').onclick = () => withBusy($('researchAnalyze'), '正在综合分析...', async () => {
      try {
        if (!state.researchTask) throw new Error('请先建立科研任务');
        const data = await runBackgroundTask('research_analyze', {
          task_id: state.researchTask.id,
          direction: $('researchDirection').value.trim(),
          paper_ids: selectedResearchPaperIds(),
          code_ids: selectedResearchCodeIds(),
          related_papers: selectedResearchCandidates()
        }, t('正在综合分析论文与代码', 'Analyzing papers and code'));
        state.researchTask = data.task;
        state.researchAnalysis = data.analysis;
        state.researchExperiment = null;
        renderResearchAnalysis();
        renderResearchExperiment();
        await loadResearchTasks(false);
        notify('多论文综合分析完成');
      } catch (error) { notify(error.message, true); }
    });
    $('researchCorrespondence').onclick = () => withBusy(
      $('researchCorrespondence'),
      t('检查中...', 'Checking...'),
      async () => {
        try {
          if (!state.researchTask) throw new Error(t('请先建立科研任务', 'Create a research task first'));
          await persistResearchTask();
          const paperIds = selectedResearchPaperIds();
          const codeIds = selectedResearchCodeIds();
          if (!paperIds.length || !codeIds.length) {
            throw new Error(t('请同时选择本地论文和代码项目', 'Select local papers and a code project'));
          }
          const data = await runBackgroundTask('research_correspondence', {
            task_id: state.researchTask.id,
            direction: $('researchDirection').value.trim(),
            paper_ids: paperIds,
            code_ids: codeIds
          }, t('正在核对论文与代码', 'Checking paper-code correspondence'));
          state.researchTask = data.task;
          state.researchCorrespondence = data.correspondence;
          renderResearchCorrespondence();
          await loadResearchTasks(false);
          notify(t('论文与代码对应检查完成', 'Paper-code correspondence check completed'));
        } catch (error) {
          notify(error.name === 'AbortError' ? t('检查已取消', 'Check cancelled') : error.message, error.name !== 'AbortError');
        }
      }
    );
    $('researchPlan').onclick = () => withBusy($('researchPlan'), '正在设计实验...', async () => {
      try {
        if (!state.researchTask) throw new Error('请先完成论文分析');
        const selectedIndex = $('researchDirectionIndex').value;
        const data = await runBackgroundTask('research_experiment', {
          task_id: state.researchTask.id,
          mode: $('researchExperimentMode').value,
          objective: $('researchObjective').value.trim(),
          direction_index: selectedIndex === '' ? null : Number(selectedIndex)
        }, t('正在生成实验方案', 'Generating experiment plan'));
        state.researchTask = data.task;
        state.researchExperiment = data.experiment;
        renderResearchExperiment();
        await loadResearchTasks(false);
        notify('实验方案已生成');
      } catch (error) { notify(error.message, true); }
    });
    $('researchAssess').onclick = () => withBusy($('researchAssess'), '正在评估...', async () => {
      try {
        if (!state.researchTask) throw new Error('请先生成实验方案');
        const data = await runBackgroundTask('research_assess', {
          task_id: state.researchTask.id,
          result: $('researchResult').value.trim(),
          attachment_ids: state.researchAttachments.map(item => item.id)
        }, t('正在评估实验结果', 'Assessing experiment results'));
        state.researchTask = data.task;
        renderResearchAssessment(data.assessment);
        await loadResearchTasks(false);
        notify(`Agent 决策：${data.assessment.decision}`);
      } catch (error) { notify(error.message, true); }
    });
    $('cancelBackgroundTask').onclick = async () => {
      const active = state.activeLongTask;
      if (!active) return;
      $('cancelBackgroundTask').disabled = true;
      $('backgroundTaskStatus').textContent = t('正在取消', 'Cancelling');
      try {
        if (active.type === 'background') {
          await api('/api/background/cancel', {task_id: active.id});
        } else {
          active.controller.abort();
        }
      } catch (error) {
        notify(error.message, true);
      } finally {
        $('cancelBackgroundTask').disabled = false;
      }
    };
    $('refreshArtifacts').onclick = () => withBusy(
      $('refreshArtifacts'),
      '…',
      async () => {
        try {
          await loadArtifacts(true);
          notify(t('图表清单已重建', 'Artifact list rebuilt'));
        } catch (error) {
          notify(error.message, true);
        }
      }
    );
    const uploadResearchAttachment = async file => {
      const task = await ensureResearchTask();
      const params = new URLSearchParams({
        task_id: task.id,
        filename: file.name || `pasted-${Date.now()}.png`,
        content_type: file.type || 'application/octet-stream'
      });
      const response = await fetch(`/api/research/attachment?${params}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/octet-stream'},
        body: file
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || t('附件上传失败', 'Attachment upload failed'));
      state.researchTask = data.task;
      state.researchAttachments = data.task.result_attachments || [];
      renderResearchTaskSelect();
      renderResearchAttachments();
      return data.attachment;
    };
    const uploadResearchFiles = async files => {
      for (const file of files) {
        await uploadResearchAttachment(file);
      }
      notify(t(`已添加 ${files.length} 个实验结果附件`, `${files.length} result attachment(s) added`));
    };
    $('researchResultFiles').onchange = async () => {
      const files = [...$('researchResultFiles').files];
      if (!files.length) return;
      try {
        await uploadResearchFiles(files);
      } catch (error) { notify(error.message, true); }
      finally { $('researchResultFiles').value = ''; }
    };
    $('researchResult').onpaste = event => {
      const images = [...(event.clipboardData?.files || [])].filter(file => file.type.startsWith('image/'));
      if (!images.length) return;
      event.preventDefault();
      uploadResearchFiles(images).catch(error => notify(error.message, true));
    };
    $('copyResearchPrompt').onclick = async () => {
      const prompt = $('researchPrompt').value;
      if (!prompt) return;
      try {
        await navigator.clipboard.writeText(prompt);
      } catch (_error) {
        $('researchPrompt').select();
        document.execCommand('copy');
      }
      notify('Codex Prompt 已复制');
    };
    const openSettings = async () => {
      try {
        const data = await get('/api/settings');
        $('textProvider').value = data.text?.provider || 'custom';
        $('textModel').value = data.text?.model || '';
        $('textBaseUrl').value = data.text?.base_url || '';
        $('textApiKey').value = '';
        $('textApiKey').placeholder = data.text?.api_key_hint || 'API Key';
        $('visionProvider').value = data.vision?.provider || 'disabled';
        $('visionModel').value = data.vision?.model || '';
        $('visionBaseUrl').value = data.vision?.base_url || '';
        $('visionApiKey').value = '';
        $('visionApiKey').placeholder = data.vision?.api_key_hint || '视觉模型 API Key';
        $('appLanguage').value = data.language || state.language;
        $('settingsModal').classList.add('open');
      } catch (error) { notify(error.message, true); }
    };
    $('openSettings').onclick = openSettings;
    $('closeSettings').onclick = $('cancelSettings').onclick = () => $('settingsModal').classList.remove('open');
    $('settingsModal').onclick = event => {
      if (event.target === $('settingsModal')) $('settingsModal').classList.remove('open');
    };
    $('closeHistory').onclick = () => $('historyModal').classList.remove('open');
    $('historyModal').onclick = event => {
      if (event.target === $('historyModal')) $('historyModal').classList.remove('open');
    };
    $('saveSettings').onclick = () => withBusy($('saveSettings'), '保存中...', async () => {
      try {
        const saved = await api('/api/settings', {
          language: $('appLanguage').value,
          text: {
            provider: $('textProvider').value,
            model: $('textModel').value,
            base_url: $('textBaseUrl').value,
            api_key: $('textApiKey').value
          },
          vision: {
            provider: $('visionProvider').value,
            model: $('visionModel').value,
            base_url: $('visionBaseUrl').value,
            api_key: $('visionApiKey').value
          }
        });
        state.language = saved.language || $('appLanguage').value || 'zh';
        localizeUi();
        renderDocs();
        renderSelected();
        renderReadingState();
        renderArtifacts();
        $('settingsModal').classList.remove('open');
        notify(t('API 设置已保存', 'API settings saved'));
      } catch (error) { notify(error.message, true); }
    });
    const toggleInspector = () => $('inspector').classList.toggle('open');
    $('inspectorToggle').onclick = toggleInspector;
    $('mobileInspector').onclick = toggleInspector;
    $('libraryToggle').onclick = () => $('library').classList.toggle('open');
    document.addEventListener('click', event => {
      if (!state.docMenuId || event.target.closest('.doc-entry')) return;
      state.docMenuId = null;
      renderDocs();
    });

    const initializeApp = async () => {
      try {
        const settings = await get('/api/settings');
        state.language = settings.language || 'zh';
      } catch (_error) {
        state.language = 'zh';
      }
      localizeUi();
      setWorkspace('reading');
      await loadDocs();
      localizeUi();
    };
    initializeApp().catch(error => notify(error.message, true));
  </script>
</body>
</html>"""
