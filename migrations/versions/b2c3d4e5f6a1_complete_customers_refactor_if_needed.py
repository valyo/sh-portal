"""complete customers refactor if migration was partially applied

If bookings still has 'email' column, add customer_id, migrate data, drop old columns.
Safe to run when refactor is already complete (no-op).

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-03-07

"""
from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6a1'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def _column_exists(conn, table, column):
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns(table)]
    return column in cols


def upgrade():
    conn = op.get_bind()
    # Only run if bookings still has old schema (email column)
    if not _column_exists(conn, 'bookings', 'email'):
        return

    # Add customer_id if missing
    if not _column_exists(conn, 'bookings', 'customer_id'):
        with op.batch_alter_table('bookings', schema=None) as batch_op:
            batch_op.add_column(sa.Column('customer_id', sa.Integer(), nullable=True))
    if not _column_exists(conn, 'bookings_lamm', 'customer_id'):
        with op.batch_alter_table('bookings_lamm', schema=None) as batch_op:
            batch_op.add_column(sa.Column('customer_id', sa.Integer(), nullable=True))

    email_to_id = {}

    def get_or_create_customer_id(email, name, telephone, address, postnummer, ort):
        if email in email_to_id:
            return email_to_id[email]
        conn.execute(sa.text(
            'INSERT INTO customers (email, name, telephone, address, postnummer, ort) '
            'VALUES (:email, :name, :telephone, :address, :postnummer, :ort)'
        ), {'email': email, 'name': name, 'telephone': telephone, 'address': address,
            'postnummer': postnummer, 'ort': ort})
        r = conn.execute(sa.text('SELECT id FROM customers WHERE email = :email'), {'email': email})
        cid = r.scalar()
        email_to_id[email] = cid
        return cid

    result = conn.execute(sa.text(
        'SELECT id, email, name, telephone, address, postnummer, ort FROM bookings'
    ))
    for row in result:
        bid, email, name, telephone, address, postnummer, ort = row
        cid = get_or_create_customer_id(email, name, telephone, address, postnummer, ort)
        conn.execute(sa.text('UPDATE bookings SET customer_id = :cid WHERE id = :bid'),
                    {'cid': cid, 'bid': bid})

    result = conn.execute(sa.text(
        'SELECT id, email, name, telephone, address, postnummer, ort FROM bookings_lamm'
    ))
    for row in result:
        bid, email, name, telephone, address, postnummer, ort = row
        cid = get_or_create_customer_id(email, name, telephone, address, postnummer, ort)
        conn.execute(sa.text('UPDATE bookings_lamm SET customer_id = :cid WHERE id = :bid'),
                    {'cid': cid, 'bid': bid})

    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_column('email')
        batch_op.drop_column('name')
        batch_op.drop_column('telephone')
        batch_op.drop_column('address')
        batch_op.drop_column('postnummer')
        batch_op.drop_column('ort')
        batch_op.alter_column('customer_id', nullable=False)
        batch_op.create_foreign_key('fk_bookings_customer_id', 'customers', ['customer_id'], ['id'])

    with op.batch_alter_table('bookings_lamm', schema=None) as batch_op:
        batch_op.drop_column('email')
        batch_op.drop_column('name')
        batch_op.drop_column('telephone')
        batch_op.drop_column('address')
        batch_op.drop_column('postnummer')
        batch_op.drop_column('ort')
        batch_op.alter_column('customer_id', nullable=False)
        batch_op.create_foreign_key('fk_bookings_lamm_customer_id', 'customers', ['customer_id'], ['id'])


def downgrade():
    # No-op: we don't revert a partial fix; full downgrade is in a1b2c3d4e5f6
    pass
