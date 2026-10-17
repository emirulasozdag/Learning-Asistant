from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Tüm ORM modellerinin tabanı. Alembic autogenerate bu metadata'yı okur."""
