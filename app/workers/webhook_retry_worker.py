
"""Poll the database and retry failed webhook events with bounded attempts."""

import os
import time
import traceback

from app.db.session import SessionLocal
from app.services.webhook_retry_service import retry_batch


def main():
    interval = max(2, int(os.getenv("WEBHOOK_RETRY_INTERVAL_SECONDS", "10")))
    batch_size = max(1, int(os.getenv("WEBHOOK_RETRY_BATCH_SIZE", "100")))

    while True:
        db = SessionLocal()

        try:
            result = retry_batch(db, batch_size=batch_size)

            if result["selected"]:
                print(f"webhook retry batch: {result}", flush=True)

        except Exception:
            db.rollback()
            print("webhook retry worker error:", flush=True)
            traceback.print_exc()

        finally:
            db.close()

        time.sleep(interval)


if __name__ == "__main__":
    main()
