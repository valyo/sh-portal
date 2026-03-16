"""Flask commands runable in container."""

# Imports

# Standard
import csv
import re
from datetime import datetime

# Installed
import click
import flask

# Own
from sh_portal import db

@click.command("create-admin")
@click.option("--github_id", "-ghid", type=str, required=True)
@click.option("--github_name", "-ghn", type=str, required=True)
@click.option("--name", "-n", type=str, required=True)
@click.option("--email", "-e", type=str, required=True)
@flask.cli.with_appcontext
def create_new_admin(
    github_id,
    github_name,
    name,
    email,
):
    """Create a new admin.

    Use name and id from github account info, but not email.  
    """
    from sh_portal import models

    error_message = ""
    if re.findall(r"[^0-9]", github_id):
        error_message = "The 'github_id' can only contain numbers."
    elif github_id[0] in [".", "-"]:
        error_message = "The 'github_id' must begin with a letter or number."

    if error_message:
        flask.current_app.logger.error(error_message)
        return

    new_admin = models.Admin(
        github_id=github_id,
        github_name=github_name,
        name=name,
        email=email,
    )
    db.session.add(new_admin)
    db.session.commit()

    flask.current_app.logger.info(f"Admin '{name}' created")


def _normalize_customer_name(s):
    """Trim and collapse multiple spaces. Apply small curation (e.g. fix double space, consistent casing for known cases)."""
    if not s or not s.strip():
        return None
    s = " ".join(s.split()).strip()
    if s.lower() == "jonny flygare":
        s = "Jonny Flygare"
    return s or None


def _parse_price(s):
    """Parse Swedish price string like '450.00 kr' or '1,800.00 kr' to float."""
    if not s or not s.strip():
        return None
    s = s.replace(" ", "").replace("kr", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _parse_kg(s):
    """Parse burk/kg string like '2.55 kg' to float or return None. Empty string -> None."""
    if not s or not s.strip():
        return None
    m = re.match(r"^([\d,.]+)\s*kg\s*$", s.strip(), re.IGNORECASE)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    return None


@click.command("import-sales")
@click.argument("csv_path", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Only report what would be imported, do not write to DB.")
@flask.cli.with_appcontext
def import_sales(csv_path, dry_run):
    """Import sales from CSV (totalt_försäljning format).

    Columns: Timestamp, sort, skörd, burk, unit_price, antal, konsistens, bigård, kategori, kund, ...
    Rules: skörd from timestamp year when empty; konsistens default 'fast'; bigård default 'Solberg';
    customer names trimmed and normalized.
    """
    from sh_portal.models import Sale, Product, SaleCategory

    created_products = 0
    created_sales = 0
    errors = []

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        if not header:
            flask.current_app.logger.error("CSV has no header row.")
            return
        # Expect: Timestamp, sort, skörd, burk, unit_price, antal, konsistens, bigård, kategori, kund, ...
        col = {h.strip(): i for i, h in enumerate(header)}
        for name in ("Timestamp", "sort", "unit_price", "antal", "kategori", "kund"):
            if name not in col:
                flask.current_app.logger.error(f"CSV missing column: {name}. Found: {list(col.keys())}")
                return

        for row_num, row in enumerate(reader, start=2):
            if len(row) < 10:
                continue
            try:
                ts_str = row[col["Timestamp"]].strip()
                ts = datetime.strptime(ts_str[:10], "%Y-%m-%d") if ts_str else None
                if not ts:
                    errors.append(f"Row {row_num}: invalid Timestamp")
                    continue

                sort_name = row[col["sort"]].strip() if col["sort"] < len(row) else ""
                skord_raw = row[col.get("skörd", 2)].strip() if col.get("skörd", 2) < len(row) else ""
                skord = skord_raw if skord_raw and skord_raw.lower() != "okänd" else str(ts.year)
                if not skord:
                    skord = str(ts.year)

                burk_raw = row[col.get("burk", 3)].strip() if col.get("burk", 3) < len(row) else ""
                burk = burk_raw if burk_raw else None

                antal_s = row[col["antal"]].strip() if col["antal"] < len(row) else ""
                try:
                    quantity = int(antal_s) if antal_s else 0
                except ValueError:
                    errors.append(f"Row {row_num}: invalid antal '{antal_s}'")
                    continue
                if quantity < 0:
                    errors.append(f"Row {row_num}: negative antal")
                    continue

                konsistens_raw = row[col.get("konsistens", 6)].strip() if col.get("konsistens", 6) < len(row) else ""
                consistency = konsistens_raw if konsistens_raw in ("fast", "flytande", "fryst") else "fast"

                bigard_raw = row[col.get("bigård", 7)].strip() if col.get("bigård", 7) < len(row) else ""
                apiary = bigard_raw if bigard_raw else "Solberg"

                kategori_name = row[col["kategori"]].strip() if col["kategori"] < len(row) else ""
                if not kategori_name:
                    errors.append(f"Row {row_num}: missing kategori")
                    continue
                category = SaleCategory.query.filter_by(name=kategori_name).first()
                if not category:
                    errors.append(f"Row {row_num}: unknown category '{kategori_name}'")
                    continue

                kund_raw = row[col["kund"]].strip() if col["kund"] < len(row) else ""
                customer_name = _normalize_customer_name(kund_raw)

                unit_price = _parse_price(row[col["unit_price"]]) if col["unit_price"] < len(row) else None
                if unit_price is None:
                    errors.append(f"Row {row_num}: invalid unit_price")
                    continue

                if not sort_name:
                    errors.append(f"Row {row_num}: missing sort")
                    continue
                product = Product.query.filter_by(name=sort_name).first()
                if not product:
                    if dry_run:
                        created_products += 1
                        created_sales += 1
                        continue
                    product = Product(name=sort_name)
                    db.session.add(product)
                    db.session.flush()
                    created_products += 1

                if dry_run:
                    created_sales += 1
                    continue

                sale = Sale(
                    timestamp=ts,
                    product_id=product.id,
                    skord=skord,
                    burk=burk,
                    unit_price=unit_price,
                    quantity=quantity,
                    consistency=consistency,
                    apiary=apiary,
                    category_id=category.id,
                    customer_id=None,
                    customer_name=customer_name,
                    invoice_id=None,
                )
                db.session.add(sale)
                created_sales += 1
            except Exception as e:
                errors.append(f"Row {row_num}: {e}")

    if not dry_run and created_sales:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flask.current_app.logger.error(f"Commit failed: {e}")
            return

    if dry_run:
        flask.current_app.logger.info(f"DRY RUN: would create {created_sales} sales, {created_products} new products.")
    else:
        flask.current_app.logger.info(f"Created {created_sales} sales, {created_products} new products.")
    for err in errors[:20]:
        flask.current_app.logger.warning(err)
    if len(errors) > 20:
        flask.current_app.logger.warning(f"... and {len(errors) - 20} more errors.")
