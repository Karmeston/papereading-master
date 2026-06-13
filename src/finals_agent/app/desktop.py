from __future__ import annotations

import ctypes
import multiprocessing
from pathlib import Path
from threading import Thread
import traceback

from finals_agent.app.web import PaperAgentRequestHandler
from finals_agent.core.config import PROJECT_ROOT, ensure_data_dirs, load_settings
from finals_agent.core.observability import configure_logging


APP_TITLE = "Papereading Master Beta"


def main() -> None:
    multiprocessing.freeze_support()
    try:
        _run_desktop()
    except Exception as exc:
        _write_crash_log(exc)
        ctypes.windll.user32.MessageBoxW(
            0,
            f"{APP_TITLE} failed to start.\n\n{exc}\n\nSee desktop-error.log in:\n{PROJECT_ROOT}",
            APP_TITLE,
            0x10,
        )
        raise


def _run_desktop() -> None:
    import webview
    from http.server import ThreadingHTTPServer

    settings = load_settings(validate=False)
    ensure_data_dirs(settings.paths)
    configure_logging(debug=settings.runtime.debug)
    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperAgentRequestHandler)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_port}/"
    server_thread = Thread(
        target=server.serve_forever,
        name="papereading-master-local-server",
        daemon=True,
    )
    server_thread.start()
    try:
        webview.create_window(
            APP_TITLE,
            url=url,
            width=1440,
            height=920,
            min_size=(980, 680),
            text_select=True,
        )
        storage_path = PROJECT_ROOT / "webview"
        storage_path.mkdir(parents=True, exist_ok=True)
        webview.start(
            private_mode=False,
            storage_path=str(storage_path),
        )
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=3)


def _write_crash_log(exc: Exception) -> None:
    try:
        PROJECT_ROOT.mkdir(parents=True, exist_ok=True)
        path = Path(PROJECT_ROOT) / "desktop-error.log"
        path.write_text(
            "".join(traceback.format_exception(exc)),
            encoding="utf-8",
        )
    except OSError:
        pass


if __name__ == "__main__":
    main()
