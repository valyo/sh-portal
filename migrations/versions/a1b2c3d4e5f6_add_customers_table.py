"""add customers table and refactor bookings to use customer_id

Revision ID: a1b2c3d4e5f6
Revises: 09eac370b337
Create Date: 2026-03-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '09eac370b337'
branch_labels = None
depends_on = None


def _table_exists(conn, name):
    """Return True if table exists."""
    insp = sa.inspect(conn)
    return name in insp.get_table_names()


def _column_exists(conn, table, column):
    """Return True if column exists on table."""
    insp = sa.inspect(conn)
    cols = [c['name'] for c in insp.get_columns(table)]
    return column in cols


def upgrade():
    conn = op.get_bind()

    # 1. Create customers table only if it doesn't exist (safe to re-run after partial run)
    if not _table_exists(conn, 'customers'):
        op.create_table(
            'customers',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('email', sa.String(length=150), nullable=False),
            sa.Column('name', sa.String(length=150), nullable=False),
            sa.Column('telephone', sa.String(length=50), nullable=False),
            sa.Column('address', sa.String(length=200), nullable=False),
            sa.Column('postnummer', sa.String(length=10), nullable=False),
            sa.Column('ort', sa.String(length=100), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )

    # 2. Add customer_id only if missing
    if not _column_exists(conn, 'bookings', 'customer_id'):
        with op.batch_alter_table('bookings', schema=None) as batch_op:
            batch_op.add_column(sa.Column('customer_id', sa.Integer(), nullable=True))

    if not _column_exists(conn, 'bookings_lamm', 'customer_id'):
        with op.batch_alter_table('bookings_lamm', schema=None) as batch_op:
            batch_op.add_column(sa.Column('customer_id', sa.Integer(), nullable=True))

    # 3. Data migration only if bookings still has old columns (email)
    if _column_exists(conn, 'bookings', 'email'):
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

    # 4. Drop old columns and set FK only if old columns still exist
    if _column_exists(conn, 'bookings', 'email'):
        with op.batch_alter_table('bookings', schema=None) as batch_op:
            batch_op.drop_column('email')
            batch_op.drop_column('name')
            batch_op.drop_column('telephone')
            batch_op.drop_column('address')
            batch_op.drop_column('postnummer')
            batch_op.drop_column('ort')
            batch_op.alter_column('customer_id', nullable=False)
            batch_op.create_foreign_key('fk_bookings_customer_id', 'customers', ['customer_id'], ['id'])

    if _column_exists(conn, 'bookings_lamm', 'email'):
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
    # Re-add columns, copy from customers, drop customer_id and FK, drop customers table
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(150), nullable=True))
        batch_op.add_column(sa.Column('name', sa.String(150), nullable=True))
        batch_op.add_column(sa.Column('telephone', sa.String(50), nullable=True))
        batch_op.add_column(sa.Column('address', sa.String(200), nullable=True))
        batch_op.add_column(sa.Column('postnummer', sa.String(10), nullable=True))
        batch_op.add_column(sa.Column('ort', sa.String(100), nullable=True))

    with op.batch_alter_table('bookings_lamm', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(150), nullable=True))
        batch_op.add_column(sa.Column('name', sa.String(150), nullable=True))
        batch_op.add_column(sa.Column('telephone', sa.String(50), nullable=True))
        batch_op.add_column(sa.Column('address', sa.String(200), nullable=True))
        batch_op.add_column(sa.Column('postnummer', sa.String(10), nullable=True))
        batch_op.add_column(sa.Column('ort', sa.String(100), nullable=True))

    conn = op.get_bind()
    # Copy customer data back (SQLite-compatible subquery form)
    conn.execute(sa.text(
        'UPDATE bookings SET email = (SELECT email FROM customers WHERE id = bookings.customer_id), '
        'name = (SELECT name FROM customers WHERE id = bookings.customer_id), '
        'telephone = (SELECT telephone FROM customers WHERE id = bookings.customer_id), '
        'address = (SELECT address FROM customers WHERE id = bookings.customer_id), '
        'postnummer = (SELECT postnummer FROM customers WHERE id = bookings.customer_id), '
        'ort = (SELECT ort FROM customers WHERE id = bookings.customer_id)'
    ))
    conn.execute(sa.text(
        'UPDATE bookings_lamm SET email = (SELECT email FROM customers WHERE id = bookings_lamm.customer_id), '
        'name = (SELECT name FROM customers WHERE id = bookings_lamm.customer_id), '
        'telephone = (SELECT telephone FROM customers WHERE id = bookings_lamm.customer_id), '
        'address = (SELECT address FROM customers WHERE id = bookings_lamm.customer_id), '
        'postnummer = (SELECT postnummer FROM customers WHERE id = bookings_lamm.customer_id), '
        'ort = (SELECT ort FROM customers WHERE id = bookings_lamm.customer_id)'
    ))

    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_constraint('fk_bookings_customer_id', type_='foreignkey')
        batch_op.drop_column('customer_id')

    with op.batch_alter_table('bookings_lamm', schema=None) as batch_op:
        batch_op.drop_constraint('fk_bookings_lamm_customer_id', type_='foreignkey')
        batch_op.drop_column('customer_id')

    op.drop_table('customers')
