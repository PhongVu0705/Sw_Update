"""Terminal entry point with the same backend services as the desktop app."""

from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.logging_config import configure_logging


def main():
    log_path = configure_logging()
    import logging

    try:
        from backend.cli import run
        return run()
    except Exception:
        logging.getLogger(__name__).exception("Terminal application failed")
        print(f"Application failed (exit code 1). Log: {log_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
