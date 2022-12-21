from flask import Flask

from webapp.models import db

app = Flask(__name__)
app.config.from_pyfile('settings.py')
db.init_app(app)

from webapp import views
