from webapp.models import db
from webapp import app

with app.app_context():
    db.create_all()
