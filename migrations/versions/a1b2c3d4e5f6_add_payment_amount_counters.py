"""Persist captured and refunded amount counters."""
import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "9c21e10d4b7a"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("transactions", sa.Column("captured_amount", sa.Numeric(15, 2), nullable=False, server_default="0.00"))
    op.add_column("transactions", sa.Column("refunded_amount", sa.Numeric(15, 2), nullable=False, server_default="0.00"))
    op.add_column("processed_webhook_events", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("processed_webhook_events", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))

def downgrade():
    op.drop_column("processed_webhook_events", "last_attempt_at")
    op.drop_column("processed_webhook_events", "attempt_count")
    op.drop_column("transactions", "refunded_amount")
    op.drop_column("transactions", "captured_amount")
