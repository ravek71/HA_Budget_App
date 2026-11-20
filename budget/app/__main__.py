"""Entry point: REST API server + recurring-expense month rollover."""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime

from .config import settings
from .data import BudgetData
from .server import make_app

log = logging.getLogger("budget")


def _seconds_to_first_day_local() -> float:
    """Seconds (from now) until the next 1st-of-month 00:05 local time."""
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(os.environ.get("TZ", "Europe/Warsaw"))
    except Exception:  # noqa: BLE001
        tz = ZoneInfo("Europe/Warsaw")
    now = datetime.now(tz)
    year, month = now.year, now.month + 1
    if month > 12:
        month, year = 1, year + 1
    target = datetime(year, month, 1, 0, 5, tzinfo=tz)
    return max(60.0, (target - now).total_seconds())


def main() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    data = BudgetData(settings.db_path)
    log.info("SQLite database: %s", settings.db_path)

    def rollover_loop() -> None:
        while True:
            sleep_s = _seconds_to_first_day_local()
            log.info("next recurring booking in %.1f h", sleep_s / 3600.0)
            time.sleep(sleep_s)
            if not settings.auto_recurring:
                continue
            try:
                added = data.apply_recurring(datetime.now().date())
                if added:
                    log.info("recurring: dodano %d transakcji stałych", added)
            except Exception:  # noqa: BLE001 - keep the loop alive
                log.exception("recurring job failed")

    threading.Thread(target=rollover_loop, name="recurring", daemon=True).start()

    app = make_app(data)
    log.info("HTTP API listening on 0.0.0.0:%d", settings.port)
    app.run(host="0.0.0.0", port=settings.port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
