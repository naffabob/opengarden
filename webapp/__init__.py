import sentry_sdk
from flask import Flask
from sentry_sdk.integrations.flask import FlaskIntegration

from webapp.models import db
from webapp.settings import SENTRY_DSN

sentry_sdk.init(
    dsn=SENTRY_DSN,
    integrations=[
        FlaskIntegration(),
    ],
    traces_sample_rate=1.0
)

app = Flask(__name__)
app.config.from_pyfile('settings.py')
db.init_app(app)

from webapp import views
