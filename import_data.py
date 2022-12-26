import csv
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError
from tqdm import tqdm

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
    normalized_data = data.split('://')[1]
    return normalized_data


# Преобразовать name с '/' в name, без '/'
def normalize_url(data: str) -> str:
    normalized_data = data.split('/')[0]
    return normalized_data


# Убрать ',' и ' ' , '/' в ресурсах
def normalize_simbols(data: str) -> str:
    normalized_data = data.strip(' ')
    normalized_data = normalized_data.strip(',')
    normalized_data = normalized_data.strip('/')
    normalized_data = normalized_data.strip('.')
    return normalized_data


# Преобразовать несколько ресурсов/ip в список ресурсов
def normalize_n(data: str) -> list:
    normalize_data = data.split('\n')
    return normalize_data


# Преобразовать список ресурсов через запятую
def normalize_list(data: str) -> list:
    normalized_data = data.split(', ')
    return normalized_data


def get_domains(data: str) -> list[str]:
    normalized_data = None
    if '\n' in data:
        normalized_data = normalize_n(data)
        data = normalized_data

    if ', ' in data:
        normalized_data = normalize_list(data)
        data = normalized_data

    if isinstance(data, str):
        normalized_data = [data]

    normalized_domains = []

    for domain in normalized_data:
        if 'http' in domain:
            normalized_domains.append(normalize_http_https(domain))
        else:
            normalized_domains.append(domain)

    normalized_domains_set = set()

    for domain in normalized_domains:
        if '/' in domain:
            norm_domain = normalize_url(domain)
            strip_domain = normalize_simbols(norm_domain)
            normalized_domains_set.add(strip_domain)
        else:
            strip_domain = normalize_simbols(domain)
            normalized_domains_set.add(strip_domain)

    normalized_domains = list(normalized_domains_set)

    return normalized_domains


def get_ips(data: str) -> list[str]:
    normalized_data = None
    if '\n' in data:
        normalized_data = normalize_n(data)

    if ', ' in data:
        normalized_data = normalize_list(data)
        data = normalized_data

    if isinstance(data, str):
        normalized_data = [data]

    return normalized_data


def get_date(data: str) -> Optional[datetime]:
    if not data:
        return None
    return parse_date(data)


with open(FILE_NAME, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f, delimiter=';')
    resources = []
    for row in reader:

        # IPs with domain name isn't interesting
        if row['name']:
            domains = get_domains(row['name'])
        else:
            domains = get_ips(row['ip'])

        added_date = get_date(row['added_date'])
        description = row['description'] or None
        order = row['order'] or None
        resource_type = row['resource_type']

        for domain in domains:
            r = Resource()
            r.name = domain
            r.description = description
            r.added_date = added_date
            r.order = order
            r.resource_type = resource_type

            resources.append(r)

already_exists = []
added_resources = []

with app.app_context():
    for resource in tqdm(resources):
        db.session.add(resource)

        try:
            db.session.commit()
        except IntegrityError:
            already_exists.append(resource)
            db.session.rollback()
            continue

        for _ in range(2):
            try:
                resource.update_ips()
            except DNSConnectionError:
                print(resource.name)
                print('DNS is unreachable. RETRYING...')
                time.sleep(0.3)
            else:
                resource.status = Resource.STATUS_RESOLVED
                added_resources.append(resource)
                break

print(f'Added: {len(added_resources)}')
print(f'Already exists: {len(already_exists)}')
for _ in already_exists:
    print(_.name)
