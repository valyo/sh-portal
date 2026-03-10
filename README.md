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
