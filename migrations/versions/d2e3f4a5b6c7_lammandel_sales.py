"""Lammandel sales: link a sale to a lammandel invoice, lammkött product, lammandel category

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-11-11

A paid lammandel invoice can become a sale (product "lammkött", category "lammandel"). The sale
points at its invoice through sales.lamm_invoice_id. Consistency and apiary only make sense for
honey, so they may be empty.
"""
from alembic import op
import sqlalchemy as sa


revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lamm_invoice_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_sales_lamm_invoice_id', 'invoices_lamm', ['lamm_invoice_id'], ['id'])
        batch_op.alter_column('consistency', existing_type=sa.String(20), nullable=True)
        batch_op.alter_column('apiary', existing_type=sa.String(50), nullable=True)

    conn = op.get_bind()
    for table, name in (('sale_categories', 'lammandel'), ('products', 'lammkött')):
        exists = conn.execute(sa.text(f"SELECT 1 FROM {table} WHERE name = :name"), {"name": name}).first()
        if not exists:
            conn.execute(sa.text(f"INSERT INTO {table} (name) VALUES (:name)"), {"name": name})


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM sales WHERE lamm_invoice_id IS NOT NULL"))
    # Rows without a value would violate NOT NULL, so fill them with the old defaults first.
    conn.execute(sa.text("UPDATE sales SET consistency = 'fast' WHERE consistency IS NULL"))
    conn.execute(sa.text("UPDATE sales SET apiary = 'Solberg' WHERE apiary IS NULL"))
    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.alter_column('apiary', existing_type=sa.String(50), nullable=False)
        batch_op.alter_column('consistency', existing_type=sa.String(20), nullable=False)
        batch_op.drop_constraint('fk_sales_lamm_invoice_id', type_='foreignkey')
        batch_op.drop_column('lamm_invoice_id')
