"""
One-off manual trigger for digest_drive_writer, for confirming Drive writes
work end-to-end without waiting for tomorrow's scheduled digest_job run.

Defaults to yesterday's menap_general digest.

    python scripts/write_digest_to_drive_now.py
    python scripts/write_digest_to_drive_now.py --date 2026-08-24 --topic global_vc
"""
import argparse
import asyncio
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.services import document_store
from app.services.digest_drive_writer import write_digest_to_drive
from app.services.summarizer import TOPIC_LABELS


async def _run(target_date: date, topic_id: str) -> None:
    output = await document_store.get_topic_output_for_date(topic_id, target_date)
    if output is None:
        print(f"No stored digest found for topic_id={topic_id!r} date={target_date.isoformat()}")
        return

    label = TOPIC_LABELS.get(topic_id, topic_id)
    await write_digest_to_drive(label, output)
    print("Done — check Railway logs above for created/updated confirmation, and check Drive.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD, defaults to yesterday")
    parser.add_argument("--topic", type=str, default="menap_general", choices=list(TOPIC_LABELS.keys()))
    args = parser.parse_args()

    target_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else date.today() - timedelta(days=1)
    )

    asyncio.run(_run(target_date, args.topic))


if __name__ == "__main__":
    main()
