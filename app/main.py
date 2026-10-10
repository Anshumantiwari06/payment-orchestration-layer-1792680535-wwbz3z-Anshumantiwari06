
from fastapi import FastAPI

app = FastAPI(
    title="Payment Orchestration Layer",
    description=(
        "A backend system for payment routing, "
        "gateway failover, idempotency, and reconciliation."
    ),
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "message": "Payment Orchestration Layer is running",
        "status": "ok",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
    }
