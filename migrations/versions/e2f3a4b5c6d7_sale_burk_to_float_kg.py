"""Change sales.burk from string to numeric (burk_kg in kg).

Revision ID: e2f3a4b5c6d7
Revises: d9e0f1a2b3c4
Create Date: 2025-03-16

"""
import re
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


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


def upgrade():
    with op.batch_alter_table('sales') as batch:
        batch.add_column(sa.Column('burk_kg', sa.Float(), nullable=True))

    conn = op.get_bind()
    # Backfill from old burk (string) to burk_kg (float)
    result = conn.execute(text("SELECT id, burk FROM sales WHERE burk IS NOT NULL AND burk != ''"))
    for row in result:
        sid, burk_str = row[0], row[1]
        val = _parse_kg(burk_str) if burk_str else None
        if val is not None:
            conn.execute(text("UPDATE sales SET burk_kg = :v WHERE id = :id"), {"v": val, "id": sid})

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
