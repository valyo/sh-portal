"""Add kg_honey to season

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-08-21

"""
from alembic import op
import sqlalchemy as sa


revision = 'b4c5d6e7f8a9'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('season', schema=None) as batch_op:
        batch_op.add_column(sa.Column('kg_honey', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('season', schema=None) as batch_op:
        batch_op.drop_column('kg_honey')
