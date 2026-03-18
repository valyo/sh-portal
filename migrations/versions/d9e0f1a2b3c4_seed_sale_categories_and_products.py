"""Seed sale_categories and products

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2025-03-16

"""
from alembic import op
import sqlalchemy as sa


revision = 'd9e0f1a2b3c4'
down_revision = 'c8d9e0f1a2b3'
branch_labels = None
depends_on = None

SALE_CATEGORIES = [
    'andel', 'kollega', 'granne', 'vän', 'FB', 'REKO', 'LFN', 'övrig',
    'Internet', 'loppis', 'marknad', 'ägare', 'ÖIF', 'distributör', 'Google',
]

PRODUCTS = [
    'solberg honung', 'maskroshonung', 'blomsterhonung', 'sensommarhonung',
    'klöverhonung', 'försommarhonung', 'skogshonung', 'hockey honung',
    'bladhonung', 'flytande honung',
]


def upgrade():
    conn = op.get_bind()
    for name in SALE_CATEGORIES:
        conn.execute(sa.text("INSERT INTO sale_categories (name) VALUES (:name)"), {"name": name})
    for name in PRODUCTS:
        conn.execute(sa.text("INSERT INTO products (name) VALUES (:name)"), {"name": name})


def downgrade():
    op.execute(sa.text("DELETE FROM sale_categories"))
    op.execute(sa.text("DELETE FROM products"))
