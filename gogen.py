import getpass
import re
import sys
from itertools import chain

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
NB_BRASS_ID = 5
NB_CISCO = 3

ACTION_RESOLVE = 'resolve'
ACTION_GENERATE = 'generate'
ACTION_CONFIG_DEV = 'config_dev'
ACTION_CONFIG_ALL = 'config_all'

RESOURCES_FILE = 'resources.txt'
NETWORKS_FILE = 'networks.txt'
FAILED_FILE = 'failed_domains.txt'

USERNAME = None
PASSWORD = None

JUNIPER_ROUTERS = []


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


def configure_acl(host: netbox_client.Devices, ips: set, username: str, password: str):
    vendor = host.device_type.manufacturer.name.lower()

    host_ip = host.primary_ip4.address[:-3]

    configurator.configure(host_ip, vendor, ips, username, password)


def get_networks() -> set:
    with open(NETWORKS_FILE, 'r') as f:
        networks = {ip for ip in f.read().splitlines()}
    return networks


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('No arguments given.')

    action = sys.argv[1]

    if action == ACTION_RESOLVE:
        resolve_resources()

    elif action == ACTION_GENERATE:
        if len(sys.argv) < 3:
            raise SystemExit('No vendor argument given')

        vendor = sys.argv[2]
        if vendor not in configurator.VENDORS:
            raise SystemExit(f'Unsupported vendor {vendor}')

        print('\n'.join(configurator.generate_config(vendor, get_networks())))

    elif action == ACTION_CONFIG_DEV:
        hostname = sys.argv[2]

        nb = netbox_client.NetboxClient(NB_URL, NB_API_TOKEN)

        try:
            host = nb.get_device(hostname)
        except netbox_client.NBException as e:
            raise SystemExit(e)

        if host is None:
            raise SystemExit(f'No device in Netbox: {hostname}')

        username = USERNAME or input('Username: ')
        password = PASSWORD or getpass.getpass('Password: ')

        configure_acl(host, get_networks(), username, password)

    elif action == ACTION_CONFIG_ALL:
        nb = netbox_client.NetboxClient(NB_URL, NB_API_TOKEN)

        cisco_hosts = nb.dcim.devices.filter(status='active', role_id=NB_BRASS_ID, manufacturer_id=NB_CISCO)

        juniper_hosts = []

        for router in JUNIPER_ROUTERS:
            try:
                host = nb.get_device(router)
            except netbox_client.NBException as e:
                raise SystemExit(e)
            if host is None:
                raise SystemExit(f'No device in Netbox: {host}')

            juniper_hosts.append(host)

        all_hosts = chain(cisco_hosts, juniper_hosts)  # read about itertools.chain

        username = USERNAME or input('Username: ')
        password = PASSWORD or getpass.getpass('Password: ')

        for host in all_hosts:
            configure_acl(host, get_networks(), username, password)
