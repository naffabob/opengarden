import csv
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from resolver import DNSConnectionError
from webapp import app
from webapp.models import db, Resource

"""
Разовый импорт данных из csv в DB и резолвом ресурсов
"""

FILE_NAME = 'filename.csv'


# Преобразовать дату к правильному виду yyyy-mm-dd
def parse_date(data: str) -> datetime:
    date = datetime.strptime(data, '%d.%m.%Y')
    return date


# Убрать https:// в начале ресурсов
def normalize_http_https(data: str) -> str:
    data = data.split('://')[1]
    return data


# Преобразовать name с '/' в name, без '/'
def normalize_url(data: str) -> str:
    data = data.split('/')[0]
    return data


# Убрать ',' и ' ' , '/' в ресурсах
def normalize_simbols(data: str) -> str:
    data = data.strip(' ')
    data = data.strip(',')
    data = data.strip('/')
    return data


# Преобразовать несколько ресурсов/ip в список ресурсов
def normalize_n(data: str) -> list:
    normalize_data = data.split('\n')
    return normalize_data


with open(FILE_NAME, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f, delimiter=';')
    resources = []
    for row in reader:
        for key, value in row.items():

            if not value:
                continue

            if '\n' in value and (key == 'name' or key == 'ip'):
                normalized_value = normalize_n(value)
                value = normalized_value
                row[key] = normalized_value

            if (key == 'name' or key == 'ip') and isinstance(value, str):
                row[key] = [value]

            if key == 'added_date' and value:
                row[key] = parse_date(value)

            if key == 'name':
                for domain in value:
                    if 'http' in domain:
                        normalized_domain = normalize_http_https(domain)
                        row[key] = list(map(lambda x: x.replace(domain, normalized_domain), value))

            if key == 'name':
                for domain in value:
                    if '/' in domain:
                        normalized_domain = normalize_url(domain)
                        row[key] = list(map(lambda x: x.replace(domain, normalized_domain), value))

        resources.append(row)

already_exists = []
added_resources = []

with app.app_context():
    for res in resources:
        print(res)

        if not res['name']:
            for ip in res['ip']:
                resource = Resource()
                resource.name = ip
                resource.resource_type = res['resource_type']
                resource.order = res['order']
                resource.description = res['description']
                resource.added_date = res['added_date'] or None
                db.session.add(resource)

        else:
            for domain in res['name']:
                resource = Resource()
                resource.name = domain
                resource.resource_type = res['resource_type']
                resource.order = res['order']
                resource.description = res['description']
                resource.added_date = res['added_date'] or None
                db.session.add(resource)

        try:
            db.session.commit()
        except IntegrityError:
            already_exists.append(res)
            db.session.rollback()
            continue

        try:
            resource.update_ips()
        except DNSConnectionError:
            print('DNS is unreachable')
            quit(1)
        else:
            added_resources.append(res)

print(f'Added: {len(added_resources)}')
for _ in added_resources:
    print(_)

print('-' * 20, '\n')

print(f'Already exists: {len(already_exists)}')
for _ in already_exists:
    print(_)
