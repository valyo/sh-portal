# Solberg Honung Web Portal

A management portal for Solberg Honung, handling beekeeping (Andelsbiodling) and lamb (Lammandel) shares, bookings, and automated invoicing.

## Features

- **Season Management**: Track and manage different production years.
- **Booking Imports**: Automatically import bookings from Google Sheets using the Google Sheets API.
- **Invoice System**: Generate unique invoices and send them automatically via email.
- **Administration**: Secure login via GitHub OAuth.
- **Data Processing**: Uses Pandas for robust handling of imported sheet data.
- **Development Environment**: Fully containerized with Docker and MailCatcher for email testing.

## Tech Stack

- **Backend**: Flask, SQLAlchemy, Flask-Migrate
- **Data**: Pandas, SQLite
- **Integrations**: Google Sheets API, GitHub OAuth
- **Frontend**: Bootstrap 5, Jinja2 Templates
- **DevOps**: Docker, Docker Compose, MailCatcher

## Setup and Running

1. **Clone the repository**:
   ```bash
   git clone https://github.com/valyo/sh-portal
   cd sh_portal
   ```

2. **Environment Configuration**:
   Create a `.env` file in the root directory with the following variables:
   ```env
   SECRET_KEY=your-secret-key
   DATABASE_URL=sqlite:///instance/sh.db
   GITHUB_CLIENT_ID=your-github-id
   GITHUB_CLIENT_SECRET=your-github-secret
   GOOGLE_SHEET_ID=your-sheet-id
   ```
   Place your Google Service Account JSON key (`sh-web-portal-f370fff1378a.json`) in the root directory.

3. **Build and run using Docker Compose**:
   ```bash
   docker-compose up --build
   ```
   After changing `requirements.txt` (e.g. bumping Flask), rebuild the image so new dependencies are installed:
   ```bash
   docker-compose build --no-cache backend && docker-compose up
   ```

4. **Access the application**:
   - Web Portal: [http://localhost:8087](http://localhost:8087)
   - MailCatcher (Email testing): [http://localhost:1088](http://localhost:1088)

## Project Structure

```
.
├── main.py              # Application entry point
├── migrations.py        # Database migration script
├── requirements.txt     # Python dependencies
├── Dockerfile          # Container configuration
├── docker-compose.yml  # Multi-container orchestration
├── .env                # Environment variables (to be created)
├── sh-web-portal-f370fff1378a.json # Google Service Account key
├── sh_portal/           # Main application package
│   ├── __init__.py      # App factory and configuration
│   ├── models.py        # SQLAlchemy database models
│   ├── utils.py         # Utility functions (Sheet imports, etc.)
│   ├── home.py          # Main portal blueprint
│   ├── seasons.py       # Season management blueprint
│   ├── andelsbiodling.py # Beekeeping blueprint
│   ├── lammandel.py      # Lamb blueprint
│   ├── commands.py      # Custom Flask CLI commands
│   ├── static/          # CSS, JS, and Images
│   └── templates/       # HTML templates
├── migrations/          # Database migration history
└── instance/            # SQLite database storage
```

## Development Tools

### PDF Preview Script
A helper script `develop_pdf.py` is available to preview certificate templates locally without running the full portal. It watches the template files and regenerates a PDF preview instantly on every save.

1. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install weasyprint watchdog jinja2
   ```

3. **Run the preview script**:
   ```bash
   python develop_pdf.py
   ```
   This will generate `certificate_preview.pdf` in the root directory and update it whenever you change the HTML template sh_portal/templates/certificate_pdf_template.html

## Testing

Tests use pytest and cover the mail backend selection (cookie vs config, connection params, API).

1. **Install test dependencies** (in the same environment as the app):
   ```bash
   pip install -r requirements.txt -r requirements-dev.txt
   ```

2. **Run tests** (use `python -m pytest` so the venv’s Python is used, not a global/pyenv pytest):
   ```bash
   python -m pytest
   ```
   Or with coverage: `python -m pytest --cov=sh_portal --cov-report=term-missing`

   To run only mail-related tests: `python -m pytest tests/test_mail_utils.py tests/test_mail_backend_api.py -v`

## Administration

To create an initial admin user for GitHub OAuth login, you can use the custom Flask command:
```bash
docker-compose exec backend flask create-new-admin <github_username>
```

## Production deployment

Deploy using the production Docker Compose file and a pre-built image from GitHub Container Registry.

**Prerequisites:** Docker and Docker Compose on the server; access to ghcr.io.

### Quick start

1. **Create the deployment directory on your server:**
   ```bash
   mkdir -p /opt/sh-portal
   cd /opt/sh-portal
   ```

2. **Copy the production compose file to your server:**
   ```bash
   # From your local machine
   scp docker-compose.prod.yml user@your-server:/opt/sh-portal/docker-compose.yml
   ```

3. **Create the data directories:**
   ```bash
   mkdir -p data/instance data/invoices data/temp data/credentials
   ```

4. **Create a `.env` file** (edit values for your environment):
   ```bash
   cat > .env << 'EOF'
   # Docker image configuration
   GITHUB_REPO=your-username/sh_portal_v0.2
   VERSION=latest

   # App port (external)
   PORT=8087

   # Flask secret (change in production)
   SECRET_KEY=your-secret-key

   # GitHub OAuth (for app login)
   GITHUB_CLIENT_ID=your-github-oauth-app-client-id
   GITHUB_CLIENT_SECRET=your-github-oauth-app-client-secret
   OAUTH_REDIRECT_URI=https://your-domain.com/callback

   # Optional: Google Sheets import
   # GOOGLE_SHEET_ID=your-google-sheet-id

   # Mail configuration
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USE_TLS=True
   MAIL_USE_SSL=False
   MAIL_USERNAME=your-email@gmail.com
   MAIL_PASSWORD=your-app-password
   MAIL_DEFAULT_SENDER=your-email@gmail.com
   EOF
   ```

5. **Copy your Google Sheets credentials** (if using Google Sheets import):
   ```bash
   cp /path/to/your/service-account.json data/credentials/service-account.json
   ```

6. **Log in to GitHub Container Registry:**
   ```bash
   echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
   ```

7. **Start the application:**
   ```bash
   docker compose up -d
   ```

8. **Run database migrations** (first deploy or after updating):
   ```bash
   docker compose run --rm --entrypoint "" app flask db upgrade
   ```

### Customers and sales

Every customer is a record in the customers table, not only the andel ones. Only the name is required; email, telephone and address are optional. Customers with bookings still need those details, because invoices and certificates use them.

When you add a sale you pick an existing customer or type a new name, which is saved as a new customer (an existing customer with exactly that name is reused). Older sales that only have a free-text customer name can be converted once after upgrading:

```bash
docker compose exec backend flask link-sales-customers --dry-run   # preview
docker compose exec backend flask link-sales-customers             # apply
```

It links each name to the existing customer with exactly that name, or creates a name-only customer; names shared by several customers are skipped and listed. `flask import-sales` now creates customers the same way.

A customer can be deleted from the Customers page (Manage, then Delete customer) unless they have bookings, since bookings, invoices and certificates need a customer. Their sales stay in the sales list with the name as plain text. Do not run `link-sales-customers` again afterwards, or it recreates a customer from those names.

The same person can end up as two customers (for example with two email addresses). Open the one to keep, pick the duplicate under "Merge a duplicate into this customer", check the preview and confirm. The duplicate's bookings and sales move to the customer you opened, which keeps its own name and email (details it lacks are copied over), and the duplicate is deleted. Invoices and certificates already sent are not touched. If both customers have a booking of the same kind in the same season the merge is refused, because a customer can only have one booking per season. Names shared by two customers are skipped by `link-sales-customers` until they are merged, so merge them and run it again.

### Invoice PDF location

Generated invoice PDFs are saved under `invoices/<andelsbiodling|lammandel>/<season year>/` next to the app (`/app/invoices` in the container, which is the `./data/invoices` volume). Set `INVOICES_DIR` in `.env` to store them somewhere else. The tests always use a temporary directory and never touch the real folder.

### Cross-site request protection

State-changing requests (POST/PUT/PATCH/DELETE) whose `Origin` header names a different site are rejected with 403, and the login cookie is `SameSite=Lax`. The portal's own host (the `Host` header and the host of `OAUTH_REDIRECT_URI`) is always allowed. If you reach the portal through a proxy that rewrites the `Host` header, list the public host name(s) in `ALLOWED_ORIGIN_HOSTS` (comma separated, e.g. `portal.example.org`).

### Production directory layout

```
/opt/sh-portal/
├── docker-compose.yml      # The compose file
├── .env                    # Environment variables
└── data/
    ├── instance/           # SQLite database (sh.db)
    ├── invoices/           # Generated invoice PDFs
    ├── temp/               # Generated certificate PDFs
    └── credentials/        # Google Sheets service account JSON
```

### Updating to a new version

```bash
docker compose pull
docker compose run --rm --entrypoint "" app flask db upgrade
docker compose up -d
```

To pin a version, set `VERSION=0.2.0` (or desired tag) in `.env` and run `docker compose up -d`.

### Backup

```bash
# Create a backup
tar -czvf sh-portal-backup-$(date +%Y%m%d).tar.gz data/

# Restore
tar -xzvf sh-portal-backup-YYYYMMDD.tar.gz
```

### Logs and health

```bash
docker compose logs -f
docker compose logs --tail 100
docker compose ps
```

### Reverse proxy (Nginx example)

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8087;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
