"""Tests for honey certificate email 'återigen' (returning customer) detection."""

from datetime import datetime


def test_returning_when_prior_season_same_customer(app, customer):
    from sh_portal import db
    from sh_portal.models import Season, Bookings
    from sh_portal.utils import honey_customer_has_prior_season_booking

    with app.app_context():
        s2024 = Season(
            year="2024",
            price=100.0,
            price_lamm=200.0,
            google_sheets_link_honey="",
            sheet_range_honey="",
            google_sheets_link_lamm="",
            sheet_range_lamm="",
        )
        s2025 = Season(
            year="2025",
            price=100.0,
            price_lamm=200.0,
            google_sheets_link_honey="",
            sheet_range_honey="",
            google_sheets_link_lamm="",
            sheet_range_lamm="",
        )
        db.session.add_all([s2024, s2025])
        db.session.commit()
        db.session.refresh(s2024)
        db.session.refresh(s2025)

        b_old = Bookings(
            season_id=s2024.id,
            customer_id=customer.id,
            quantity=1,
            timestamp=datetime(2024, 1, 1),
        )
        b_new = Bookings(
            season_id=s2025.id,
            customer_id=customer.id,
            quantity=2,
            timestamp=datetime(2025, 1, 1),
        )
        db.session.add_all([b_old, b_new])
        db.session.commit()
        db.session.refresh(b_new)

        assert honey_customer_has_prior_season_booking(b_new, s2025) is True


def test_not_returning_first_season_only(app, season, booking):
    from sh_portal.utils import honey_customer_has_prior_season_booking

    with app.app_context():
        assert honey_customer_has_prior_season_booking(booking, season) is False


def test_returning_matches_email_across_duplicate_customer_rows(app):
    """Same email on two Customer rows: prior season still counts."""
    from sh_portal import db
    from sh_portal.models import Season, Bookings, Customer
    from sh_portal.utils import honey_customer_has_prior_season_booking

    with app.app_context():
        s2024 = Season(
            year="2024",
            price=100.0,
            price_lamm=200.0,
            google_sheets_link_honey="",
            sheet_range_honey="",
            google_sheets_link_lamm="",
            sheet_range_lamm="",
        )
        s2025 = Season(
            year="2025",
            price=100.0,
            price_lamm=200.0,
            google_sheets_link_honey="",
            sheet_range_honey="",
            google_sheets_link_lamm="",
            sheet_range_lamm="",
        )
        db.session.add_all([s2024, s2025])
        db.session.commit()
        db.session.refresh(s2024)
        db.session.refresh(s2025)

        c1 = Customer(
            email="dup@example.com",
            name="A",
            telephone="1",
            address="x",
            postnummer="1",
            ort="y",
        )
        c2 = Customer(
            email="dup@example.com",
            name="B",
            telephone="2",
            address="x",
            postnummer="2",
            ort="y",
        )
        db.session.add_all([c1, c2])
        db.session.commit()
        db.session.refresh(c1)
        db.session.refresh(c2)

        b_old = Bookings(
            season_id=s2024.id,
            customer_id=c1.id,
            quantity=1,
            timestamp=datetime(2024, 1, 1),
        )
        b_new = Bookings(
            season_id=s2025.id,
            customer_id=c2.id,
            quantity=1,
            timestamp=datetime(2025, 1, 1),
        )
        db.session.add_all([b_old, b_new])
        db.session.commit()
        db.session.refresh(b_new)

        assert honey_customer_has_prior_season_booking(b_new, s2025) is True
