"""
One-off resend of a stored digest email, for debugging delivery issues
without re-running the full retrieval/summarization pipeline.

Defaults to resending yesterday's digest to a single test address
(murtaza.hiraj@antler.co). Pass --all to send to the full configured
recipient list instead, and --date/--topic to target a different digest.

    python scripts/resend_digest_email.py
    python scripts/resend_digest_email.py --all
    python scripts/resend_digest_email.py --date 2026-08-24 --topic global_vc
"""
import argparse
import asyncio
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.services import document_store, email_client
from app.services.summarizer import TOPIC_LABELS

TEST_RECIPIENT = "murtaza.hiraj@antler.co"


async def _resend(target_date: date, topic_id: str, all_recipients: bool) -> None:
    output = await document_store.get_topic_output_for_date(topic_id, target_date)
    if output is None:
        print(f"No stored digest found for topic_id={topic_id!r} date={target_date.isoformat()}")
        return

    label = TOPIC_LABELS.get(topic_id, topic_id)
    subject = f"Antler MENAP Daily Digest — {label} — {output.date.isoformat()}"

    if all_recipients:
        sent = await email_client.send_digest_email(subject, output.summary_text, output.deals)
        print(f"Sent to {sent} recipient(s) from the configured list.")
    else:
        original_recipients = email_client.settings.digest_email_recipients
        email_client.settings.digest_email_recipients = TEST_RECIPIENT
        try:
            sent = await email_client.send_digest_email(subject, output.summary_text, output.deals)
        finally:
            email_client.settings.digest_email_recipients = original_recipients
        print(f"Sent to {TEST_RECIPIENT}: {'ok' if sent else 'FAILED (see logs above)'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD, defaults to yesterday")
    parser.add_argument("--topic", type=str, default="menap_general", choices=list(TOPIC_LABELS.keys()))
    parser.add_argument("--all", action="store_true", help="Send to the full configured recipient list")
    args = parser.parse_args()

    target_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else date.today() - timedelta(days=1)
    )

    asyncio.run(_resend(target_date, args.topic, args.all))


if __name__ == "__main__":
    main()
