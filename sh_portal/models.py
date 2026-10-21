import json
from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func


VAT_RATES = (6, 12)


class VatMixin:
    """Invoice totals are VAT-inclusive; derive net and VAT amounts from vat_rate.

    Both are rounded to whole öre, and the VAT is total minus net, so net + VAT always
    equals the total exactly as printed.
    """

    @property
    def vat_net(self):
        return round(self.tot_sum / (1 + self.vat_rate / 100), 2)

    @property
    def vat_amount(self):
        return round(self.tot_sum - self.vat_net, 2)


class Season(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.String(10))
    price = db.Column(db.Float, nullable=True)
    price_lamm = db.Column(db.Float, nullable=True)
    price_lamm_2 = db.Column(db.Float, nullable=True)
    kg_honey = db.Column(db.Float, nullable=True)
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


class Customer(db.Model):
    """Shared customer/contact data for bookings (andelsbiodling and lammandel)."""
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    telephone = db.Column(db.String(50), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    postnummer = db.Column(db.String(10), nullable=False)
    ort = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        return f'<Customer {self.name} ({self.email})>'


class Bookings(db.Model):
    __tablename__ = 'bookings'

    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey('season.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    message = db.Column(db.Text)
    quantity = db.Column(db.Integer, nullable=False)
    certificate_name = db.Column(db.String(150), nullable=True)
    certificate_quantity = db.Column(db.Integer, nullable=True)
    certificate_sent_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)

    season = db.relationship('Season', backref=db.backref('bookings', lazy=True))
    customer = db.relationship('Customer', backref=db.backref('bookings', lazy=True))

    @property
    def email(self):
        return self.customer.email if self.customer else None

    @property
    def name(self):
        return self.customer.name if self.customer else None

    @property
    def telephone(self):
        return self.customer.telephone if self.customer else None

    @property
    def address(self):
        return self.customer.address if self.customer else None

    @property
    def postnummer(self):
        return self.customer.postnummer if self.customer else None

    @property
    def ort(self):
        return self.customer.ort if self.customer else None

    def __repr__(self):
        return f'<Bookings {self.name} - {self.season.year}>'


class BookingsLamm(db.Model):
    __tablename__ = 'bookings_lamm'

    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey('season.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    message = db.Column(db.Text)
    quantity = db.Column(db.Integer, nullable=False)
    certificate_name = db.Column(db.String(150), nullable=True)
    certificate_quantity = db.Column(db.Integer, nullable=True)
    certificate_sent_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    andel_tiers = db.Column(db.Text, nullable=True)

    season = db.relationship('Season', backref=db.backref('bookings_lamm', lazy=True))
    customer = db.relationship('Customer', backref=db.backref('bookings_lamm', lazy=True))

    @property
    def email(self):
        return self.customer.email if self.customer else None

    @property
    def name(self):
        return self.customer.name if self.customer else None

    @property
    def telephone(self):
        return self.customer.telephone if self.customer else None

    @property
    def address(self):
        return self.customer.address if self.customer else None

    @property
    def postnummer(self):
        return self.customer.postnummer if self.customer else None

    @property
    def ort(self):
        return self.customer.ort if self.customer else None

    def get_andel_tiers(self):
        """Price tier (1 or 2) per andel, padded/truncated to quantity; defaults to tier 1."""
        try:
            tiers = [int(t) for t in json.loads(self.andel_tiers)] if self.andel_tiers else []
        except (ValueError, TypeError):
            tiers = []
        tiers = [t if t in (1, 2) else 1 for t in tiers][:self.quantity]
        return tiers + [1] * (self.quantity - len(tiers))

    def set_andel_tiers(self, raw_json):
        """Store per-andel price tiers from a JSON list; tier 2 is only allowed if the season has a second price."""
        allow_tier_2 = self.season.price_lamm_2 is not None
        tiers = [2 if (int(t) == 2 and allow_tier_2) else 1 for t in json.loads(raw_json)]
        self.andel_tiers = json.dumps(tiers)

    def andel_prices(self, season=None):
        """Unit price for each andel, resolved from the season's two Lammandel prices."""
        season = season or self.season
        price_2 = season.price_lamm_2 if season.price_lamm_2 is not None else season.price_lamm
        return [price_2 if t == 2 else season.price_lamm for t in self.get_andel_tiers()]

    def total_price(self, season=None):
        return sum(self.andel_prices(season))

    def __repr__(self):
        return f'<BookingsLamm {self.name} - {self.season.year}>'


class Invoice(VatMixin, db.Model):
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
    vat_rate = db.Column(db.Integer, nullable=False)  # always chosen explicitly when invoicing

    # Relationships
    season = db.relationship('Season', backref=db.backref('invoices', lazy=True))
    booking = db.relationship('Bookings', backref=db.backref('invoices', lazy=True))
    sale = db.relationship('Sale', backref=db.backref('invoice'), uselist=False)

    def __repr__(self):
        return f'<Invoice {self.invoice_id} for booking {self.booking_id}>'


class Product(db.Model):
    """Honey product type (sort)."""
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return f'<Product {self.name}>'


class SaleCategory(db.Model):
    """Sales channel / customer category (andel, kollega, granne, etc.)."""
    __tablename__ = 'sale_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    def __repr__(self):
        return f'<SaleCategory {self.name}>'


class Sale(db.Model):
    """A single honey sale. Can be from CSV/manual or created when an andel invoice is marked paid."""
    __tablename__ = 'sales'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    skord = db.Column(db.String(20), nullable=False)  # harvest year or "okänd"
    burk_kg = db.Column(db.Float, nullable=True)  # jar size in kg (unit always kg)
    unit_price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    consistency = db.Column(db.String(20), nullable=False, default='fast')  # fast, flytande, fryst
    apiary = db.Column(db.String(50), nullable=False, default='Solberg')
    category_id = db.Column(db.Integer, db.ForeignKey('sale_categories.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)  # portal customer (andel)
    customer_name = db.Column(db.String(200), nullable=True)  # free-text when no customer_id
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=True)  # set when created from paid andel invoice

    product = db.relationship('Product', backref=db.backref('sales', lazy=True))
    category = db.relationship('SaleCategory', backref=db.backref('sales', lazy=True))
    customer = db.relationship('Customer', backref=db.backref('sales', lazy=True))

    @property
    def total_price(self):
        return round(self.unit_price * self.quantity, 2)

    @property
    def display_customer(self):
        """Customer for display: linked Customer name or free-text customer_name."""
        if self.customer_id and self.customer:
            return self.customer.name
        return self.customer_name or '—'

    def __repr__(self):
        return f'<Sale {self.id} {self.timestamp.date()} {self.display_customer}>'


class InvoiceLamm(VatMixin, db.Model):
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
    vat_rate = db.Column(db.Integer, nullable=False)  # always chosen explicitly when invoicing

    # Relationships
    season = db.relationship('Season', backref=db.backref('invoices_lamm', lazy=True))
    booking = db.relationship('BookingsLamm', backref=db.backref('invoices_lamm', lazy=True))

    @property
    def line_items(self):
        """One invoice row per distinct unit price: (quantity, unit_price, total)."""
        prices = self.booking.andel_prices(self.season)
        items = []
        for price in sorted(set(prices)):
            qty = prices.count(price)
            items.append({'quantity': qty, 'unit_price': price, 'total': qty * price})
        return items

    def __repr__(self):
        return f'<InvoiceLamm {self.invoice_id} for booking {self.booking_id}>'

