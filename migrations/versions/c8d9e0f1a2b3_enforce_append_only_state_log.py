"""Prevent updates/deletes to the transaction state audit log."""
from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""
        CREATE OR REPLACE FUNCTION reject_transaction_state_log_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'transaction_state_log is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER transaction_state_log_append_only
        BEFORE UPDATE OR DELETE ON transaction_state_log
        FOR EACH ROW EXECUTE FUNCTION reject_transaction_state_log_mutation();
    """)

def downgrade():
    op.execute("DROP TRIGGER IF EXISTS transaction_state_log_append_only ON transaction_state_log")
    op.execute("DROP FUNCTION IF EXISTS reject_transaction_state_log_mutation()")
