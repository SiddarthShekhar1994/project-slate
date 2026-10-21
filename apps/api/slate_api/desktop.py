"""The backend of the desktop app.

    slate-api --port 8123 --data-dir "%APPDATA%\\Slate"

The Electron shell starts this (on Windows it is a PyInstaller build of this
module). It turns on desktop mode, makes the data folder, brings the SQLite
database up to date and serves the API on 127.0.0.1 only. It exits when its
standard input closes, so the backend never outlives the window that started
it, even if that window crashes.
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
import threading
from pathlib import Path


def migrations_dir() -> Path:
    bundle = getattr(sys, "_MEIPASS", None)  # inside a PyInstaller build
    if bundle:
        return Path(bundle) / "migrations"
    return Path(__file__).resolve().parents[1] / "migrations"


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(migrations_dir()))
    command.upgrade(cfg, "head")


def _exit_with_parent() -> None:
    try:
        while sys.stdin.buffer.read(1):
            pass
    except (OSError, ValueError, AttributeError):
        pass
    os._exit(0)


def main(argv: list[str] | None = None) -> None:
    # In a frozen build, worker processes re-run this executable; this hands them off.
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(prog="slate-api", description="Slate's desktop backend")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--data-dir", help="where the database, uploads and settings live")
    parser.add_argument("--watch-stdin", action="store_true", help="exit when standard input closes")
    args = parser.parse_args(argv)

    os.environ["SLATE_DESKTOP"] = "1"
    if args.data_dir:
        os.environ["SLATE_DATA_DIR"] = args.data_dir
    from .config import get_settings

    Path(get_settings().data_dir).mkdir(parents=True, exist_ok=True)
    migrate()
    if args.watch_stdin:
        threading.Thread(target=_exit_with_parent, name="parent-watch", daemon=True).start()

    import logging

    import uvicorn

    from .main import app

    # Slate's own messages (grading workers, source processing) go to the log too.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
