import uuid
from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReconciliationAnomaly(Base):
    __tablename__ = "reconciliation_anomalies"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    gateway: Mapped[str] = mapped_column(String(40), nullable=False)
    internal_status: Mapped[str] = mapped_column(String(40), nullable=False)
    gateway_status: Mapped[str] = mapped_column(String(40), nullable=False)
    amount: Mapped[object] = mapped_column(Numeric(15,2), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN")
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
