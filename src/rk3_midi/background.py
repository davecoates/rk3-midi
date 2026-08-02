"""Windowless entry point used by the packaged Scheduled Task executable."""

from __future__ import annotations

import logging
import traceback

from .config import default_log_path, load_config
from .service import run_service


def main() -> int:
    try:
        config = load_config()
        run_service(config)
    except Exception:  # noqa: BLE001 - last-resort record for no-console startup
        path = default_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log:
            log.write("rk3-midi background startup failed\n")
            log.write(traceback.format_exc())
        logging.shutdown()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
