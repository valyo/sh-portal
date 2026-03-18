"""Change sales.burk from string to numeric (burk_kg in kg).

Revision ID: e2f3a4b5c6d7
Revises: d9e0f1a2b3c4
Create Date: 2025-03-16

"""
import re
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import OperationalError


revision = 'e2f3a4b5c6d7'
down_revision = 'd9e0f1a2b3c4'
branch_labels = None
depends_on = None


def _parse_kg(s):
    """Parse burk string like '2.55 kg' or '2.5' to float or None."""
    if not s or not str(s).strip():
        return None
    s = str(s).strip()
    m = re.match(r"^([\d,.]+)\s*(?:kg\s*)?$", s, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    return None


def _has_column(conn, table, column):
    """Return True if table has the given column (SQLite). PRAGMA table_info does not support bound params for table name."""
    # Table name must be literal; we only use this for 'sales' in this migration.
    r = conn.execute(text(f'PRAGMA table_info("{table}")'))
    return any(row[1] == column for row in r)


def upgrade():
    conn = op.get_bind()
    has_burk_kg = _has_column(conn, "sales", "burk_kg")
    has_burk = _has_column(conn, "sales", "burk")

    if not has_burk_kg:
        try:
            with op.batch_alter_table('sales') as batch:
                batch.add_column(sa.Column('burk_kg', sa.Float(), nullable=True))
        except OperationalError as e:
            err = getattr(e, "orig", e)
            if "duplicate column name" not in str(err).lower():
                raise
            # Column already exists (e.g. from db.create_all()); skip

    # Backfill from old burk (string) to burk_kg (float) only if burk exists
    if has_burk:
        result = conn.execute(text("SELECT id, burk FROM sales WHERE burk IS NOT NULL AND burk != ''"))
        for row in result:
            sid, burk_str = row[0], row[1]
            val = _parse_kg(burk_str) if burk_str else None
            if val is not None:
                conn.execute(text("UPDATE sales SET burk_kg = :v WHERE id = :id"), {"v": val, "id": sid})

    if has_burk:
        with op.batch_alter_table('sales') as batch:
            batch.drop_column('burk')


def downgrade():
    with op.batch_alter_table('sales') as batch:
        batch.add_column(sa.Column('burk', sa.String(length=30), nullable=True))
    conn = op.get_bind()
    # Format burk_kg back as "X.XX kg" for downgrade
    result = conn.execute(text("SELECT id, burk_kg FROM sales WHERE burk_kg IS NOT NULL"))
    for row in result:
        sid, kg = row[0], row[1]
        if kg is not None:
            conn.execute(text("UPDATE sales SET burk = :v WHERE id = :id"), {"v": f"{kg:.2f} kg", "id": sid})
    with op.batch_alter_table('sales') as batch:
        batch.drop_column('burk_kg')
