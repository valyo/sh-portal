"""Make customer contact details optional (only the name is required)

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-10-26

Pure sales customers have no email, telephone or address. Existing rows keep their values.
"""
from alembic import op
import sqlalchemy as sa


revision = 'c1d2e3f4a5b6'
down_revision = 'b0c1d2e3f4a5'
branch_labels = None
depends_on = None

COLUMNS = (
    ('email', sa.String(150)),
    ('telephone', sa.String(50)),
    ('address', sa.String(200)),
    ('postnummer', sa.String(10)),
    ('ort', sa.String(100)),
)


def upgrade():
    with op.batch_alter_table('customers', schema=None) as batch_op:
        for name, type_ in COLUMNS:
            batch_op.alter_column(name, existing_type=type_, nullable=True)


def downgrade():
    # Rows without a value would violate NOT NULL, so fill them with an empty string first.
    for name, _ in COLUMNS:
        op.execute(f"UPDATE customers SET {name} = '' WHERE {name} IS NULL")
    with op.batch_alter_table('customers', schema=None) as batch_op:
        for name, type_ in COLUMNS:
            batch_op.alter_column(name, existing_type=type_, nullable=False)
