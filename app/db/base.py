
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

from app.models.transaction import Transaction
from app.models.transaction_state_log import TransactionStateLog