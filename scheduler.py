from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from config import load_config
from main import run_once
from utils import setup_logger


def main() -> None:
    config = load_config()
    setup_logger(level=config.log_level)

    tz = pytz.timezone(config.timezone)
    scheduler = BlockingScheduler(timezone=tz)
    trigger = CronTrigger.from_crontab(config.report_cron, timezone=tz)

    scheduler.add_job(run_once, trigger=trigger, id="daily_report")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()