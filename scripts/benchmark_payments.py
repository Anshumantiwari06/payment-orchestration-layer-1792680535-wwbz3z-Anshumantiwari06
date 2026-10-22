
import argparse
import asyncio
import json
import math
import os
import time
import uuid
from datetime import UTC, datetime

import httpx


def percentile(values, p):
    """Calculate a percentile using the nearest-rank method."""
    if not values:
        return 0.0

    ordered = sorted(values)
    index = max(0, math.ceil((p / 100) * len(ordered)) - 1)
    return ordered[min(index, len(ordered) - 1)]


async def main():
    parser = argparse.ArgumentParser(
        description="Payment API load test"
    )
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--rps", type=float, default=5)
    parser.add_argument("--duration", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=20)
    args = parser.parse_args()

    if args.rps <= 0 or args.duration <= 0 or args.concurrency <= 0:
        parser.error("rps, duration, and concurrency must be positive")

    api_key = os.getenv("API_KEY")
    headers = {"X-API-Key": api_key} if api_key else {}

    latencies = []
    statuses = {}
    errors = []

    completed = 0
    completed_within_window = 0
    requests_started = 0
    requests_started_within_window = 0
    scheduled_requests = 0

    semaphore = asyncio.Semaphore(args.concurrency)
    started_at_utc = datetime.now(UTC).isoformat()

    start = time.perf_counter()
    schedule_end = start + args.duration

    async with httpx.AsyncClient(
        timeout=15.0,
        headers=headers,
    ) as client:

        async def send_request(sequence):
            nonlocal completed
            nonlocal completed_within_window
            nonlocal requests_started
            nonlocal requests_started_within_window

            async with semaphore:
                payload = {
                    "merchant_id": "benchmark_merchant",
                    "merchant_order_id": (
                        f"bench-{uuid.uuid4().hex}-{sequence}"
                    ),
                    "amount": "125.50",
                    "currency": "INR",
                }

                request_start = time.perf_counter()
                requests_started += 1

                if request_start <= schedule_end:
                    requests_started_within_window += 1

                try:
                    response = await client.post(
                        f"{args.url.rstrip('/')}/api/v1/payments",
                        json=payload,
                    )

                    statuses[response.status_code] = (
                        statuses.get(response.status_code, 0) + 1
                    )

                    if not response.is_success:
                        errors.append({
                            "status": response.status_code,
                            "body": response.text[:300],
                        })

                except Exception as exc:
                    errors.append({
                        "error": str(exc)[:300],
                    })

                finally:
                    completion_time = time.perf_counter()
                    elapsed_ms = (
                        completion_time - request_start
                    ) * 1000

                    latencies.append(elapsed_ms)
                    completed += 1

                    if completion_time <= schedule_end:
                        completed_within_window += 1

        tasks = []
        sequence = 0
        interval = 1.0 / args.rps

        while time.perf_counter() < schedule_end:
            scheduled_at = start + sequence * interval
            delay = scheduled_at - time.perf_counter()

            if delay > 0:
                await asyncio.sleep(delay)

            if time.perf_counter() >= schedule_end:
                break

            tasks.append(
                asyncio.create_task(send_request(sequence))
            )
            sequence += 1

        scheduled_requests = sequence

        # Allow all scheduled requests to finish before reporting.
        await asyncio.gather(*tasks)

    total_elapsed = time.perf_counter() - start

    successful = sum(
        count
        for status, count in statuses.items()
        if 200 <= status < 300
    )

    completed_after_window = completed - completed_within_window

    report = {
        "started_at_utc": started_at_utc,
        "base_url": args.url,
        "target_requests_per_second": args.rps,
        "measurement_window_seconds": args.duration,
        "total_elapsed_seconds": round(total_elapsed, 3),
        "scheduled_requests": scheduled_requests,
        "requests_started": requests_started,
        "requests_started_within_window": (
            requests_started_within_window
        ),
        "completed_requests": completed,
        "completed_within_window": completed_within_window,
        "completed_after_window": completed_after_window,
        "successful_responses": successful,
        "http_status_counts": statuses,
        "error_count": len(errors),
        "scheduled_requests_per_second": round(
            scheduled_requests / args.duration, 2
        ),
        "actual_requests_per_second": round(
            completed_within_window / args.duration, 2
        ),
        "overall_completion_requests_per_second": round(
            completed / total_elapsed, 2
        ) if total_elapsed > 0 else 0.0,
        "latency_ms": {
            "p50": round(percentile(latencies, 50), 2),
            "p95": round(percentile(latencies, 95), 2),
            "p99": round(percentile(latencies, 99), 2),
            "max": round(max(latencies, default=0), 2),
        },
        "sample_errors": errors[:10],
    }

    os.makedirs("reports", exist_ok=True)
    filename = (
        f"reports/payment_benchmark_{int(time.time())}.json"
    )

    with open(filename, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    print(json.dumps(report, indent=2))
    print(f"\nReport saved to: {filename}")


if __name__ == "__main__":
    asyncio.run(main())
