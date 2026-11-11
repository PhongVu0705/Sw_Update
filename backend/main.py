"""Desktop entry point: configure logging, compose the app, report exit status."""

from pathlib import Path
import sys

# Support both `python backend/main.py` and `python -m backend.main`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.logging_config import configure_logging


def main():
    log_path = configure_logging()
    import logging

    logger = logging.getLogger(__name__)
    try:
        from backend.application import run

        return run()
    except Exception:
        logger.exception("Application startup or shutdown failed")
        print(f"Application failed (exit code 1). Log: {log_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
