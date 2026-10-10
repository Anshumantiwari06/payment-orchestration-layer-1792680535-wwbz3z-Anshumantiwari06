
from decimal import Decimal

from sqlalchemy import Numeric

from app.db.base import Base
from app.models.transaction import Transaction
from app.models.transaction_state_log import TransactionStateLog


def test_core_tables_are_registered():
    assert "transactions" in Base.metadata.tables
    assert "transaction_state_log" in Base.metadata.tables


def test_transaction_amount_uses_precise_numeric_type():
    amount_column = Transaction.__table__.columns["amount"]

    assert isinstance(amount_column.type, Numeric)
    assert amount_column.type.precision == 15
    assert amount_column.type.scale == 2
    assert Decimal("1200.50") + Decimal("99.50") == Decimal("1300.00")


def test_transaction_has_uuid_primary_key():
    id_column = Transaction.__table__.columns["id"]

    assert id_column.primary_key
    assert id_column.type.as_uuid is True


def test_state_log_references_transactions():
    transaction_id = TransactionStateLog.__table__.columns["transaction_id"]

    assert any(
        foreign_key.target_fullname == "transactions.id"
        for foreign_key in transaction_id.foreign_keys
    )


def test_transaction_required_fields_are_non_nullable():
    table = Transaction.__table__

    assert not table.columns["merchant_id"].nullable
    assert not table.columns["merchant_order_id"].nullable
    assert not table.columns["amount"].nullable
    assert not table.columns["currency"].nullable
    assert not table.columns["status"].nullable
