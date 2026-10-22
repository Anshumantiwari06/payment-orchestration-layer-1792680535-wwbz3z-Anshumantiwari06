from unittest.mock import Mock

import pytest

from app.workers import webhook_retry_worker


def test_worker_rolls_back_and_closes_session_on_error(monkeypatch):
    db = Mock()
    sleep_calls = 0

    monkeypatch.setattr(webhook_retry_worker, "SessionLocal", lambda: db)

    def fail_retry_batch(db, batch_size):
        raise RuntimeError("simulated retry failure")

    monkeypatch.setattr(
        webhook_retry_worker, "retry_batch", fail_retry_batch
    )

    def stop_after_one_iteration(interval):
        nonlocal sleep_calls
        sleep_calls += 1
        raise KeyboardInterrupt

    monkeypatch.setattr(webhook_retry_worker.time, "sleep", stop_after_one_iteration)

    monkeypatch.setattr(webhook_retry_worker, "traceback", Mock())

    with pytest.raises(KeyboardInterrupt):
        webhook_retry_worker.main()

    db.rollback.assert_called_once()
    db.close.assert_called_once()
    assert sleep_calls == 1
def test_worker_prints_result_when_events_are_selected(monkeypatch, capsys):
    db = Mock()

    monkeypatch.setattr(webhook_retry_worker, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        webhook_retry_worker,
        "retry_batch",
        lambda db, batch_size: {"selected": 2, "retried": 2},
    )

    def stop_after_one_iteration(interval):
        raise KeyboardInterrupt

    monkeypatch.setattr(
        webhook_retry_worker.time, "sleep", stop_after_one_iteration
    )

    with pytest.raises(KeyboardInterrupt):
        webhook_retry_worker.main()

    output = capsys.readouterr().out
    assert "webhook retry batch:" in output
    assert "'selected': 2" in output
    db.close.assert_called_once()