from time import sleep

from loguru import logger
from tqdm import tqdm

from webapp import app
from webapp.models import Resource, DNSResolveError, DNSConnectionError
from webapp.settings import LOG_FILE, LOG_LEVEL

logger.add(
    LOG_FILE,
    level=LOG_LEVEL,
    format="{time} {level} {message}",
    rotation="1 MB",
    compression="zip",
    retention="7 days",
)

app = app

failed_resources = []

with app.app_context():
    resources = Resource.query.all()
    for resource in tqdm(resources):
        try:
            resource.update_ips()
        except (DNSResolveError, DNSConnectionError):
            failed_resources.append(resource)
        sleep(0.3)

    logger.info(f'FAILED TO RESOLVE {len(failed_resources)} RESOURCES: ')
    for resource in failed_resources:
        logger.info(resource.name)
