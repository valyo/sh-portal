"""rename number to quantity in bookings tables

Revision ID: e9107734564c
Revises: 17ca9a98d31a
Create Date: 2025-05-09 17:38:41.294372

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e9107734564c'
down_revision = '17ca9a98d31a'
branch_labels = None
depends_on = None


def upgrade():
    # For bookings table
    op.execute('ALTER TABLE bookings RENAME COLUMN number TO quantity')

    # For bookings_lamm table
    op.execute('ALTER TABLE bookings_lamm RENAME COLUMN number TO quantity')


def downgrade():
    # For bookings table
    op.execute('ALTER TABLE bookings RENAME COLUMN quantity TO number')

    # For bookings_lamm table
    op.execute('ALTER TABLE bookings_lamm RENAME COLUMN quantity TO number')
