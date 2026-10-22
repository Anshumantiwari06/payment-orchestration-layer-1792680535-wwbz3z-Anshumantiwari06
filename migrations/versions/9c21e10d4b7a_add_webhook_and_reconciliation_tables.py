"""Add webhook deduplication and reconciliation anomaly tables."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "9c21e10d4b7a"
down_revision = "36435a4dfc99"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("processed_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("gateway", sa.String(40), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("transaction_id", sa.String(36)),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="RECEIVED"),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("gateway", "event_id", name="uq_webhook_gateway_event"))
    op.create_table("reconciliation_anomalies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", sa.String(36), nullable=False),
        sa.Column("gateway", sa.String(40), nullable=False),
        sa.Column("internal_status", sa.String(40), nullable=False),
        sa.Column("gateway_status", sa.String(40), nullable=False),
        sa.Column("amount", sa.Numeric(15,2), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="OPEN"),
        sa.Column("details", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_reconciliation_anomalies_transaction_id", "reconciliation_anomalies", ["transaction_id"])

def downgrade():
    op.drop_index("ix_reconciliation_anomalies_transaction_id", table_name="reconciliation_anomalies")
    op.drop_table("reconciliation_anomalies")
    op.drop_table("processed_webhook_events")
