import os

basedir = os.path.abspath(os.path.dirname(__file__))

SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, '', '../db_name.db')
SQLALCHEMY_ECHO = True
SQLALCHEMY_TRACK_MODIFICATIONS = False

SECRET_KEY = 'SECRET_KEY'
DEBUG = True

PREFIX = '/og'

NB_URL = 'netbox-url'
NB_API_TOKEN = 'netbox-token'
NB_BRASS_ID = 5
NB_CISCO = 3

JUNIPER_ROUTERS = ['r1', 'r2']

username = 'user'
password = 'pass'

SENTRY_DSN = 'SENTRY_DSN'

LOG_FILE = '/var/log/og.log'
LOG_LEVEL = 'INFO'
