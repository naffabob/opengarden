import re
from enum import Enum
from ipaddress import IPv4Network

from loguru import logger
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException
from tqdm import tqdm

import netbox_client
from webapp.settings import NB_BRASS_ID, NB_CISCO

VENDOR_JUNIPER = 'juniper'
VENDOR_CISCO = 'cisco'

VENDORS = {VENDOR_JUNIPER, VENDOR_CISCO}

# ACL names on brasses
ACL_NAMES_OUT = [
    'OG-OUT',
    'FROM-OG',
    'FROM-OGv4',
    'ACL_OUT_OG',
    'FROM-OPENGARDEN',
    'FROM-OPEN-GARDEN',
    'FROM-OPEN-GARDEN-2',
    'FROM-OPEN-GARDEN-1.8',
]

ACL_NAMES_IN = [
    'TO-OG',
    'OG-IN',
    'TO-OGv4',
    'ACL_IN_OG',
    'TO-OPENGARDEN',
    'TO-OPEN-GARDEN',
    'TO-OPEN-GARDEN-2',
    'TO-OPEN-GARDEN-1.8',
]


class OGTimeoutException(Exception):
    pass


class OGAuthenticationException(Exception):
    pass


class NetboxConnectionError(Exception):
    pass


class NetboxDeviceError(Exception):
    pass


class Status(Enum):
    OK = 1
    NOACL = 2
    UPTODATE = 3


def retrieve_acl_names(c: ConnectHandler) -> tuple:
    og_in = ''
    og_out = ''
    output = c.send_command('sh access-lists | i list')
    for acl in ACL_NAMES_OUT:
        if acl in output:
            og_out = acl

    for acl in ACL_NAMES_IN:
        if acl in output:
            og_in = acl

    return og_in, og_out


def configure(host: str, vendor: str, ips: set, username: str, password: str):
    if vendor not in VENDORS:
        raise ValueError(f'Unknown vendor {vendor}')
    if vendor == VENDOR_CISCO:
        return configure_cisco(host, ips, username, password)
    elif vendor == VENDOR_JUNIPER:
        return configure_juniper(host, ips, username, password)


def netlist_cisco(c: ConnectHandler, og_in: str, og_out: str) -> set:
    result = set()
    host_regexp = r'\d+\.\d+\.\d+\.\d+'
    data = c.send_config_set(
        [
            f'do show ip access-lists {og_in}',
            f'show ip access-lists {og_out}',
        ]
    )

    for line in data.splitlines():
        if 'permit' in line:
            ip_mask = re.findall(host_regexp, line)
            if len(ip_mask) > 1:
                ip = ip_mask[0]
                wild_mask = ip_mask[1]
                network = IPv4Network(f'{ip}/{wild_mask}')
                result.add(f'{ip}/{network.prefixlen}')
            else:
                result.add(''.join(ip_mask))
    return result


def netlist_juniper(c: ConnectHandler) -> set:
    result = set()
    data = c.send_command('show configuration groups rdr-nomoney-routes')
    for line in data.splitlines():
        parts = line.split()
        if 'route' in parts:
            netw = parts[1]
            if '/32' in netw:
                host = netw.split('/')[0]
                result.add(host)
            else:
                result.add(netw)
    return result


def get_diff(host: str, vendor: str, resolved_ips: set, username: str, password: str) -> dict:
    diff_dict = {
        'status': Status.OK,
        'to_delete': set(),
        'to_add': set(),
    }

    if vendor not in VENDORS:
        raise ValueError(f'Unknown vendor {vendor}')
    if vendor == VENDOR_CISCO:
        try:
            c = ConnectHandler(
                host=host,
                username=username,
                password=password,
                device_type='cisco_ios_telnet',
            )
        except NetmikoAuthenticationException:
            raise OGAuthenticationException from None
        except NetmikoTimeoutException:
            raise OGTimeoutException from None

        og_in, og_out = retrieve_acl_names(c)

        if not og_in and not og_out:
            diff_dict['status'] = Status.NOACL
            return diff_dict

        current_ips = netlist_cisco(c, og_in, og_out)

        if current_ips == resolved_ips:
            diff_dict['status'] = Status.UPTODATE
            return diff_dict

        diff_dict['to_delete'] = sorted(current_ips - resolved_ips)
        diff_dict['to_add'] = sorted(resolved_ips - current_ips)

    elif vendor == VENDOR_JUNIPER:
        try:
            c = ConnectHandler(
                host=host,
                username=username,
                password=password,
                device_type='juniper_junos',
            )
        except NetmikoAuthenticationException:
            raise OGAuthenticationException from None
        except NetmikoTimeoutException:
            raise OGTimeoutException from None

        current_ips = netlist_juniper(c)

        if current_ips == resolved_ips:
            diff_dict['status'] = Status.UPTODATE
            return diff_dict

        diff_dict['to_delete'] = sorted(current_ips - resolved_ips)
        diff_dict['to_add'] = sorted(resolved_ips - current_ips)

    return diff_dict


def print_diff(current_ips: set, resolved_ips: set):
    to_delete = current_ips - resolved_ips
    to_add = resolved_ips - current_ips
    print('IPs to delete:')  # For console user interface
    for ip in to_delete:
        print(ip)
    print('IPs to add:')  # For console user interface
    for ip in to_add:
        print(ip)

    return to_delete, to_add


def configure_cisco(host: str, ips: set, username: str, password: str):
    try:
        c = ConnectHandler(
            host=host,
            username=username,
            password=password,
            device_type='cisco_ios_telnet',
        )
    except NetmikoAuthenticationException:
        raise OGAuthenticationException
    except NetmikoTimeoutException:
        raise OGTimeoutException

    og_in, og_out = retrieve_acl_names(c)

    current_ips = netlist_cisco(c, og_in, og_out)
    if current_ips == ips:
        logger.info(f'{host} is up to date')
        return

    print_diff(current_ips, ips)

    if input(f'Would you like to update {host}? (y/n): ') != 'y':
        return

    commands = generate_cisco(ips, og_in, og_out)

    c.config_mode()

    chunk_size = 25

    for start_id in tqdm(range(0, len(commands), chunk_size)):
        c.send_config_set(
            commands[start_id:start_id + chunk_size],
            enter_config_mode=False,
            exit_config_mode=False,
            cmd_verify=False,
            read_timeout=25,
        )

    c.exit_config_mode()

    c.send_command('write')
    c.disconnect()


def configure_juniper(host: str, ips: set, username: str, password: str):
    try:
        c = ConnectHandler(
            host=host,
            username=username,
            password=password,
            device_type='juniper_junos',
        )
    except NetmikoAuthenticationException:
        raise OGAuthenticationException
    except NetmikoTimeoutException:
        raise OGTimeoutException

    current_ips = netlist_juniper(c)

    if current_ips == ips:
        logger.info(f'{host} is up to date')
        return

    print_diff(current_ips, ips)

    if input(f'Would you like to update {host}? (y/n): ') != 'y':
        return

    commands = generate_juniper(ips)
    commands.append('commit')
    c.send_config_set(commands, config_mode_command='configure exclusive')
    c.disconnect()


def generate_config(vendor: str, ips: set, host: str, username: str, password: str) -> dict:
    config = {
        'status': Status.OK,
        'config_lines': []
    }

    if vendor not in VENDORS:
        raise ValueError(f'Unknown vendor {vendor}')
    if vendor == VENDOR_CISCO:
        try:
            c = ConnectHandler(
                host=host,
                username=username,
                password=password,
                device_type='cisco_ios_telnet',
            )
        except NetmikoAuthenticationException:
            raise OGAuthenticationException
        except NetmikoTimeoutException:
            raise OGTimeoutException

        og_in, og_out = retrieve_acl_names(c)

        if not og_in and not og_out:
            config['status'] = Status.NOACL
            return config

        config['config_lines'] = generate_cisco(ips, og_in, og_out)
        return config

    elif vendor == VENDOR_JUNIPER:
        config['config_lines'] = generate_juniper(ips)
        return config


def generate_cisco(ips: set, acl_name_in: str, acl_name_out: str) -> list:
    og_out = [
        f'no ip access-list extended {acl_name_out}',
        f'ip access-list extended {acl_name_out}',
    ]
    og_in = [
        f'no ip access-list extended {acl_name_in}',
        f'ip access-list extended {acl_name_in}',
    ]

    for ip in ips:
        if '/' in ip:
            net = IPv4Network(ip)
            og_out.append(f'permit ip {net.network_address} {net.hostmask} any')
            og_in.append(f'permit ip any {net.network_address} {net.hostmask}')
        else:
            og_out.append(f'permit ip host {ip} any')
            og_in.append(f'permit ip any host {ip}')
    og_out.append('deny ip any any')
    og_in.append('deny ip any any')
    return og_in + og_out


def generate_juniper(ips: set) -> list:
    result = ['delete groups rdr-nomoney-routes routing-instances <*> routing-options static']
    for ip in ips:
        if '/' not in ip:
            ip += '/32'
        result.append(
            f'set groups rdr-nomoney-routes routing-instances <*> routing-options static route {ip} next-table inet.0'
        )
    return result


def get_juniper_hosts(nb: netbox_client, allowed_routers: list) -> list[netbox_client]:
    juniper_hosts = []

    for router in allowed_routers:
        try:
            host = nb.get_device(router)
        except netbox_client.NBException:
            raise NetboxConnectionError
        if host is None:
            raise NetboxDeviceError

        juniper_hosts.append(host)
    return juniper_hosts


def get_cisco_hosts(nb: netbox_client) -> list[netbox_client]:
    try:
        cisco_hosts = nb.dcim.devices.filter(status='active', role_id=NB_BRASS_ID, manufacturer_id=NB_CISCO)
    except netbox_client.NBException:
        raise NetboxConnectionError

    if cisco_hosts is None:
        raise NetboxDeviceError

    return cisco_hosts
