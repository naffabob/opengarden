import re
import sys

from loguru import logger
from requests.exceptions import ConnectionError

import configurator
import netbox_client
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
    except ConnectionError as e:
        raise SystemExit(e)

    ips.update(resolved_ips)

    with open(NETWORKS_FILE, 'w') as f:
        for ip in ips:
            f.write(f'{ip}\n')

    with open(FAILED_FILE, 'w') as f:
        for domain in failed_domains:
            f.write(f'{domain}\n')

    print(f'{len(ips)} networks saved to {NETWORKS_FILE}.')
    print(f'{len(failed_domains)} FAILED domains saved to {FAILED_FILE}.')


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
        print('\n'.join(configurator.generate_config(vendor, ips)))

    elif action == ACTION_CONFIG_DEV:
        hostname = sys.argv[2]

        nb = netbox_client.NetboxClient(NB_URL, NB_API_TOKEN)
        host = nb.get_device(hostname)

        if host is None:
            raise SystemExit(f'No device in Netbox: {hostname}')

        vendor = host.device_type.manufacturer.name.lower()

        host_ip = host.primary_ip4.address[:-3]

        with open(NETWORKS_FILE, 'r') as f:
            ips = {ip for ip in f.read().splitlines()}
        print('\n'.join(configurator.generate_config(vendor, ips)))

        if input(f'Configure {host.name} - {host_ip}? y/n: ') == 'y':
            configurator.configure(host_ip, vendor, ips)
        else:
            raise SystemExit(f'Configure canceled')

    elif action == ACTION_CONFIG_ALL:
        raise SystemExit(f'NOT implemented {action}')

    else:
        raise SystemExit(f'Unknown argument {action}')
