import re
import sys

import pynetbox
from loguru import logger

import configurator
import resolver

logger.add(
    'gogen.log',
    level='INFO',
    format='{time} {level} {message}',
    rotation='10 MB',
    compression='zip',
)

NB_URL = 'https://netbox-url'
NB_API_TOKEN = 'token'

ACTION_RESOLVE = 'resolve'
ACTION_GENERATE = 'generate'
ACTION_CONFIG_DEV = 'config_dev'
ACTION_CONFIG_ALL = 'config_all'

RESOURCES_FILE = 'resources.txt'
NETWORKS_FILE = 'networks.txt'
FAILED_FILE = 'failed_domains.txt'


def resolve_resources():
    ips = set()
    domains = set()

    ip_pattern = r'\d{1,}\.\d{1,}\.\d{1,}\.\d{1,}'

    with open(RESOURCES_FILE, 'r') as f:
        resources = f.read().splitlines()

    for resource in resources:
        if re.match(ip_pattern, resource):
            if resource.endswith('/32'):
                resource = resource[:-3]
            ips.add(resource)
        else:
            domains.add(resource)

    try:
        resolved_ips, failed_domains = resolver.resolve_domains(domains)
    except ValueError as e:
        raise SystemExit(e)

    ips.update(resolved_ips)

    with open(NETWORKS_FILE, 'w') as f:
        for ip in ips:
            f.write(f'{ip}\n')

    with open(FAILED_FILE, 'w') as f:
        for domain in failed_domains:
            f.write(f'{domain}\n')

    print(f'{len(ips)} networks saved to {NETWORKS_FILE}.')
    print(f'{len(failed_domains)} FILED domains saved to {FAILED_FILE}.')


def get_netbox_device(hostname: str):
    try:
        nb = pynetbox.api(NB_URL, NB_API_TOKEN)
    except Exception as e:
        logger.error(e)
        quit(1)
    dev = nb.dcim.devices.get(name=hostname)
    if dev:
        return dev
    else:
        raise SystemExit(f'No such device in Netbox.')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit(f'No arguments given.')

    action = sys.argv[1]

    if action == ACTION_RESOLVE:
        resolve_resources()

    elif action == ACTION_GENERATE:
        if len(sys.argv) < 3:
            raise SystemExit(f'No vendor argument given')

        vendor = sys.argv[2]
        if vendor not in configurator.VENDORS:
            raise SystemExit(f'Unsupported vendor {vendor}')

        with open(NETWORKS_FILE, 'r') as f:
            ips = f.read().splitlines()
        print(configurator.generate_config(vendor, ips))

    elif action == ACTION_CONFIG_DEV:
        hostname = sys.argv[2]
        host = get_netbox_device(hostname)
        vendor = host.device_type.manufacturer.name.lower()
        with open(NETWORKS_FILE, 'r') as f:
            ips = f.read().splitlines()
        print(configurator.generate_config(vendor, ips))
        raise SystemExit(f'NOT implemented {action}')

    elif action == ACTION_CONFIG_ALL:
        raise SystemExit(f'NOT implemented {action}')

    else:
        raise SystemExit(f'Unknown argument {action}')
