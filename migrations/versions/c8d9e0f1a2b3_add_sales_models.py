"""Add sales models (Product, SaleCategory, Sale)

Revision ID: c8d9e0f1a2b3
Revises: b2c3d4e5f6a1
Create Date: 2025-03-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError


revision = 'c8d9e0f1a2b3'
down_revision = 'b2c3d4e5f6a1'
branch_labels = None
depends_on = None


def _create_if_not_exists(name, create_fn):
    """Run create_fn(); ignore OperationalError if table/index already exists (e.g. from db.create_all())."""
    try:
        create_fn()
    except OperationalError as e:
        msg = (str(e.orig) if getattr(e, "orig", None) else str(e)).lower()
        if "already exists" not in msg:
            raise


def upgrade():
    _create_if_not_exists("products", lambda: op.create_table(
        'products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    ))
    _create_if_not_exists("sale_categories", lambda: op.create_table(
        'sale_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    ))
    _create_if_not_exists("sales", lambda: op.create_table(
        'sales',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('skord', sa.String(length=20), nullable=False),
        sa.Column('burk', sa.String(length=30), nullable=True),
        sa.Column('unit_price', sa.Float(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('consistency', sa.String(length=20), nullable=False),
        sa.Column('apiary', sa.String(length=50), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('customer_name', sa.String(length=200), nullable=True),
        sa.Column('invoice_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['category_id'], ['sale_categories.id'], ),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.PrimaryKeyConstraint('id'),
    ))
    try:
        op.create_index(op.f('ix_sales_invoice_id'), 'sales', ['invoice_id'], unique=True)
    except OperationalError as e:
        msg = (str(e.orig) if getattr(e, "orig", None) else str(e)).lower()
        if "already exists" not in msg:
            raise


def downgrade():
    op.drop_index(op.f('ix_sales_invoice_id'), table_name='sales')
    op.drop_table('sales')
    op.drop_table('sale_categories')
    op.drop_table('products')
