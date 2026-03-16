# Sales CSV Analysis & Design Decisions

Analysis of `totalt_försäljning-v2 - totalt.csv` (930 rows) before implementing sales management.

---

## 1. CSV structure issues

### 1.1 Duplicate column name: `pris`

- **Issue:** The header has **two columns named `pris`**: column 5 (unit price) and column 14 (total price).
- **Effect:** When using a standard CSV reader (e.g. Python `csv.DictReader`), the second `pris` overwrites the first, so **total price is lost** if you use dict keys.
- **Decision:** When reading the file, use column **indices** (e.g. column 13 for total price) or rename headers on read (e.g. `pris_enhet`, `pris_totalt`).

### 1.2 Redundant columns (as you noted)

- **månad** and **år** are derivable from **Timestamp**. Omit in DB; derive in queries/UI if needed.

### 1.3 Derived columns

- **kg** = `burk` (weight per unit) × **antal**. In the CSV this holds for all rows.
- **Total price** = unit price × **antal**. Also consistent in the CSV.
- **Decision:** Store **unit price** and **quantity**; compute total and total kg in the app, or store both for display/import fidelity.

---

## 2. Data types and formats

### 2.1 Timestamp

- Format: `YYYY-MM-DD`. All 930 rows parse as valid dates. No issues.

### 2.2 sort (honey type)

- **Type:** Free text (product name).
- **Values (examples):** `solberg honung` (828), `maskroshonung` (30), `blomsterhonung` (23), `sensommarhonung` (21), `klöverhonung` (17), `försommarhonung` (6), `skogshonung` (2), `hockey honung` (1), `bladhonung` (1), `flytande honung` (1).
- **Decision:** Either keep as string on Sale, or add a **Product/Sort** table (id, name) and reference it from Sale for consistency and filtering. Latter is better if you want to manage products (e.g. prices per sort).

### 2.3 skörd (harvest year)

- **Type:** Mixed: integer year (`2019`–`2025`) or literal **`okänd`** (666 rows).
- **Decision:** Store as **string** (e.g. `"2021"` or `"okänd"`), or use **nullable integer** with `NULL` for “okänd”. Same choice in UI (dropdown: years + “Okänd”).

### 2.4 burk (jar size)

- **Format:** `"X.XX kg"` (e.g. `2.55 kg`, `0.35 kg`). One row has **empty burk** (line 148) with only unit price; that row is a special case.
- **Decision:** Store as **string** as-is for display, or parse to **numeric** (e.g. `Decimal`) and store unit as kg. If you normalize, handle the one empty-burk row (impute or flag).

### 2.5 pris (prices)

- **Format:** Swedish: `"450.00 kr"` or `"1,800.00 kr"` (comma as thousands separator). All values parse correctly after stripping spaces and `kr` and replacing `,`.
- **Decision:** Store as **numeric** (e.g. `Decimal` or `Float`). No “kr” in DB.

### 2.6 konsistens (consistency)

- **Values:** `fast` (243), `flytande` (12), `fryst` (9), **empty** (666, mainly older rows).
- **Decision:** **Nullable** or allow empty string; in UI treat empty as “not specified” or “—”.

### 2.7 bigård (apiary)

- **Values:** `Solberg` (71), `Harbo` (22), `Käbo` (10), **empty** (827).
- **Decision:** Optional FK to an **Apiary** table (id, name) or optional string on Sale. Normalize if you need reporting per apiary.

### 2.8 kategori (category)

- **Values:** e.g. `kollega` (257), `andel` (201), `granne` (159), `vän` (104), `FB` (50), `REKO` (34), `LFN` (31), `övrig` (24), `Internet` (21), `loppis` (19), `marknad` (8), `ägare` (8), `ÖIF` (7), `distributör` (6), `Google` (1).
- **Decision:** Fits well as its **own table** `SaleCategory` (id, name) with FK on Sale. Gives stable list for filters and reports.

---

## 3. Kund (customer) and link to existing Customer model

### 3.1 What the CSV has

- **kund** is a single text field: person names, companies, placeholders (`loppis`, `ÖIF`), multiple names (`Erika, Fia, Jenny`), or company + contact (`Svekon, Att: Sofi Widolf`). **No** email, phone, or address in the CSV.

### 3.2 Existing app model

- **Customer** in `models.py` is for andelsbiodling (and lammandel): **email, name, telephone, address, postnummer, ort** (all required). So it’s a “registered” contact, not just a name.

### 3.3 Mismatch

- Many sales are **not** to registered customers (kollega, granne, vän, loppis, etc.). Only **andel** (201 rows) might overlap with people who are also in the portal as Customers.
- Even for andel, matching CSV “kund” to `Customer.name` is fragile (spaces, spelling, “Jonny” vs “jonny”).

### 3.4 Recommended design

- **Sale** has:
  - **customer_id** (nullable FK to **Customer**) for “this sale is linked to a portal customer”.
  - **customer_name** (nullable string): display name from CSV or manual entry (e.g. “Erika, Fia, Jenny”, “loppis J”, “Svekon, Att: Sofi Widolf”).
- **Business rule:** If `customer_id` is set, you can show `Customer.name` (and optionally allow overriding with `customer_name`). If only `customer_name` is set, show that. So “kund” in the app = either linked Customer or free-text name.
- **Import:** For existing CSV, import into `customer_name` only. Optionally later: tool or UI to “link this sale to a Customer” by choosing from existing Customers (and maybe normalizing names for andel).

---

## 4. Data quality issues to fix or allow

### 4.1 Empty kund (2 rows)

- **Lines 107 and 815:** `kategori=andel` but **kund** is empty.
- **Options:** (a) Leave as NULL/empty and allow “andel without name” in UI, (b) Set to a placeholder e.g. “Okänd kund”, (c) Manually fill and re-export.

### 4.2 Empty burk (1 row)

- **Line 148:** `burk` empty, unit price `360.00 kr`, antal 1. So total = 360 kr, kg unknown.
- **Options:** (a) Store `burk` as NULL and total price only; (b) Impute e.g. from price (if you have a rule); (c) Mark row as “needs review” and still import with NULL burk.

### 4.3 Kund name variants (same person, different spelling)

- **Example:** `Jonny Flygare` vs `jonny Flygare` (2 rows). If you later link to Customer, you’ll want to normalize (e.g. trim, optional title-case) and/or merge duplicates.
- **Decision:** Accept as-is for import; add optional “normalize/merge customer names” in a later step if you introduce a SalesCustomer or link to Customer.

### 4.4 Trailing spaces in names

- Some **kund** values have trailing spaces (e.g. `Jennifer Westblom `). **Recommendation:** Trim on import and in forms.

### 4.5 Double space in name

- e.g. **Håkan  Roos** (double space). Trim and optionally normalize spaces on import.

---

## 5. Summary: decisions before implementation

| Topic | Recommendation |
|-------|----------------|
| **CSV reading** | Use column index for 14th column (total price) or rename headers to `pris_enhet` / `pris_totalt`. |
| **Redundant columns** | Do not store `månad`, `år`; derive from `Timestamp`. |
| **kg / total price** | Store unit price + quantity; compute total and total kg, or also store for import fidelity. |
| **sort** | Either string on Sale or separate Product/Sort table (id, name). |
| **skörd** | String or nullable integer; treat “okänd” as NULL or literal. |
| **burk** | String or numeric (kg); handle 1 row with empty burk (NULL or impute). |
| **konsistens / bigård** | Optional string or FK to small lookup tables. |
| **kategori** | Separate table `SaleCategory` (id, name), FK on Sale. |
| **Kund** | Sale: optional `customer_id` (FK to Customer) + optional `customer_name` (text). Import CSV “kund” into `customer_name`; link to Customer only where applicable (e.g. andel). |
| **Empty kund (2 rows)** | Allow NULL or placeholder; decide policy for andel. |
| **Empty burk (1 row)** | Allow NULL; optionally flag for review. |
| **Name normalization** | Trim and optional “merge duplicates” later; fix “Jonny”/“jonny” and “Håkan  Roos” on import. |

---

## 6. Suggested model sketch (for implementation phase)

- **SaleCategory** – id, name (e.g. andel, kollega, granne).
- **Sale** – id, timestamp, sort (string or product_id), skörd (string or int?), burk (string or decimal), unit_price, quantity, consistency, apiary (string or fk), category_id (FK), customer_id (nullable FK to Customer), customer_name (nullable string). No månad/år; total and total_kg computed or stored as you prefer.

After you confirm these decisions (and whether you want Product/Sort and Apiary as tables), implementation can follow this consistently.

---

## 7. Implementation summary (done)

- **Product** and **SaleCategory** tables added; **Sale** has product_id, category_id, customer_id (nullable), customer_name (nullable), invoice_id (nullable).
- **skörd:** When empty or "okänd", derived from sale timestamp year in CSV import and when creating sale from invoice (season.year).
- **konsistens:** Default `fast` when empty (import and invoice-created sales).
- **bigård:** Default `Solberg` when empty (import and invoice-created sales).
- **Kund:** Sale has both `customer_id` (FK to Customer) and `customer_name` (free text). Andel sales created from **paid invoice** set `invoice_id` and `customer_id` from the booking; CSV import sets only `customer_name` (with trim/normalize). Display uses `display_customer` (linked customer name or customer_name).
- **Invoice paid → Sale:** When an andel invoice is marked as paid, a **Sale** is created (product "solberg honung", category "andel", customer from booking, skörd from season year). When the invoice is later marked unpaid, that sale is deleted.
- **CSV import:** `flask import-sales path/to/file.csv` (optional `--dry-run`). Applies curation (trim/normalize names, default consistency/apiary, skörd from timestamp). New products are created if missing.
- **Sales UI:** `/sales` list with filters by year, category, product; table shows date, product, skörd, burk, qty, prices, category, customer, and whether the sale came from an invoice.
