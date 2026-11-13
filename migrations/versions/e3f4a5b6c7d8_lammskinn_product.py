"""Add the lammskinn product

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-11-11

Lamb skins are sold by quantity and price, like the lammkött added in d2e3f4a5b6c7.
"""
from alembic import op
import sqlalchemy as sa


revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if not conn.execute(sa.text("SELECT 1 FROM products WHERE name = 'lammskinn'")).first():
        conn.execute(sa.text("INSERT INTO products (name) VALUES ('lammskinn')"))


def downgrade():
    # Sales of the product go with it (sales.product_id is NOT NULL).
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM sales WHERE product_id IN (SELECT id FROM products WHERE name = 'lammskinn')"))
    conn.execute(sa.text("DELETE FROM products WHERE name = 'lammskinn'"))
