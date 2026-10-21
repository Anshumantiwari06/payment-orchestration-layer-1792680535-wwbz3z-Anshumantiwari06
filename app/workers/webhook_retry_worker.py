"""Poll the database and retry failed webhook events with bounded attempts."""
import os
import time
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
        except Exception as exc:
            db.rollback()
            print(f"webhook retry worker error: {type(exc).__name__}", flush=True)
        finally:
            db.close()
        time.sleep(interval)

if __name__ == "__main__":
    main()
