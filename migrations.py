from flask_migrate import Migrate, upgrade, init, migrate as migrate_fn
from sh_portal import create_app, db
import os

app = create_app()
migrate = Migrate(app, db)

if __name__ == '__main__':
    with app.app_context():
        # Only initialize if the migrations directory doesn't exist
        if not os.path.exists('migrations'):
            print("Initializing migrations folder...")
            init()
        else:
            print("Migrations folder already exists, skipping init.")

        print("Creating migration script...")
        try:
            migrate_fn(message="add_certificate_name")
        except Exception as e:
            # This might fail if there are no changes to detect, which is fine
            print(f"Migration generation info: {e}")

        print("Applying migrations to database...")
        upgrade()
        print("Migrations complete!")