"""auto provision public users on signup

Revision ID: 6d172efc3511
Revises: 1e6859fa4e56
Create Date: 2026-08-20 14:30:00.968596

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6d172efc3511'
down_revision: Union[str, Sequence[str], None] = '1e6859fa4e56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Supabase Auth writes new users straight into auth.users — this trigger
    # mirrors each one into public.users so chat_threads' FK (and the RLS
    # policies scoped to public.users) have a row to point at immediately.
    op.execute(
        "CREATE FUNCTION public.handle_new_user() "
        "RETURNS trigger "
        "LANGUAGE plpgsql "
        "SECURITY DEFINER "
        "SET search_path = public "
        "AS $$ "
        "BEGIN "
        "  INSERT INTO public.users (id, email) VALUES (NEW.id, NEW.email); "
        "  RETURN NEW; "
        "END; "
        "$$"
    )
    op.execute(
        "CREATE TRIGGER on_auth_user_created "
        "AFTER INSERT ON auth.users "
        "FOR EACH ROW EXECUTE FUNCTION public.handle_new_user()"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users")
    op.execute("DROP FUNCTION IF EXISTS public.handle_new_user()")
