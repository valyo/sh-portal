from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func


class Season(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.String(10))
    price = db.Column(db.Float, nullable=True)
    price_lamm = db.Column(db.Float, nullable=True)
    google_sheets_link_honey = db.Column(db.String(500), nullable=True)
    sheet_range_honey = db.Column(db.String(100), nullable=True)
    google_sheets_link_lamm = db.Column(db.String(500), nullable=True)
    sheet_range_lamm = db.Column(db.String(100), nullable=True)
    
    def __repr__(self):
        return f'<Season {self.year}>'


class Admin(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    github_id = db.Column(db.Integer, unique=True)
    github_name = db.Column(db.String(150))
    name = db.Column(db.String(150))
    email = db.Column(db.String(150), unique=True)
    # password = db.Column(db.String(150))


class Bookings(db.Model):
    __tablename__ = 'bookings'

    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey('season.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    email = db.Column(db.String(150), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    telephone = db.Column(db.String(50), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    postnummer = db.Column(db.String(10), nullable=False)
    ort = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text)
    quantity = db.Column(db.Integer, nullable=False)
    certificate_name = db.Column(db.String(150), nullable=True)
    certificate_quantity = db.Column(db.Integer, nullable=True)

    # Relationship with Season
    season = db.relationship('Season', backref=db.backref('bookings', lazy=True))

    def __repr__(self):
        return f'<Bookings {self.name} - {self.season.year}>'


class BookingsLamm(db.Model):
    __tablename__ = 'bookings_lamm'

    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey('season.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    email = db.Column(db.String(150), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    telephone = db.Column(db.String(50), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    postnummer = db.Column(db.String(10), nullable=False)
    ort = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text)
    quantity = db.Column(db.Integer, nullable=False)
    certificate_name = db.Column(db.String(150), nullable=True)
    certificate_quantity = db.Column(db.Integer, nullable=True)

    # Relationship with Season
    season = db.relationship('Season', backref=db.backref('bookings_lamm', lazy=True))

    def __repr__(self):
        return f'<BookingsLamm {self.name} - {self.season.year}>'


class Invoice(db.Model):
    __tablename__ = 'invoices'

    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey('season.id'), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    invoice_id = db.Column(db.String(50), unique=True, nullable=False)
    date_created = db.Column(db.DateTime, default=db.func.current_timestamp())
    sent = db.Column(db.Boolean, default=False)
    date_payed = db.Column(db.DateTime, nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    tot_sum = db.Column(db.Float, nullable=False)

    # Relationships
    season = db.relationship('Season', backref=db.backref('invoices', lazy=True))
    booking = db.relationship('Bookings', backref=db.backref('invoices', lazy=True))

    def __repr__(self):
        return f'<Invoice {self.invoice_id} for booking {self.booking_id}>'


class InvoiceLamm(db.Model):
    __tablename__ = 'invoices_lamm'

    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey('season.id'), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings_lamm.id'), nullable=False)
    invoice_id = db.Column(db.String(50), unique=True, nullable=False)
    date_created = db.Column(db.DateTime, default=db.func.current_timestamp())
    sent = db.Column(db.Boolean, default=False)
    date_payed = db.Column(db.DateTime, nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    tot_sum = db.Column(db.Float, nullable=False)

    # Relationships
    season = db.relationship('Season', backref=db.backref('invoices_lamm', lazy=True))
    booking = db.relationship('BookingsLamm', backref=db.backref('invoices_lamm', lazy=True))

    def __repr__(self):
        return f'<InvoiceLamm {self.invoice_id} for booking {self.booking_id}>'

