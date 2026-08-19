
from sqlalchemy import Column, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Reference-only stub for Supabase's managed auth.users table, so
# users.id's FK has a target to resolve against. Alembic must never
# create/alter/drop this — see include_object in alembic/env.py.
auth_users = Table(
    "users",
    Base.metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    schema="auth",
)
