# init_db.py
from app import app, db  # Import the app and db instances from your Flask app

# Create the database and tables
with app.app_context():
    db.create_all()
