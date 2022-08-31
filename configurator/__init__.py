import re
from ipaddress import IPv4Network
from tqdm import tqdm
from loguru import logger
from netmiko import ConnectHandler

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
    data = c.send_config_set([f'show ip access-lists {og_in}', f'show ip access-lists {og_out}'])
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


def print_diff(current_ips: set, resolved_ips: set):
    to_delete = current_ips - resolved_ips
    to_add = resolved_ips - current_ips
    print('IPs to delete:')
    for ip in to_delete:
        print(ip)
    print('IPs to add:')
    for ip in to_add:
        print(ip)


def configure_cisco(host: str, ips: set, username: str, password: str):
    c = ConnectHandler(
        host=host,
        username=username,
        password=password,
        device_type='cisco_ios_telnet',
    )

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
    c = ConnectHandler(
        host=host,
        username=username,
        password=password,
        device_type='juniper_junos',
    )
    current_ips = netlist_juniper(c)

    if current_ips == ips:
        logger.info(f'{host} is up to date')
        return

    print_diff(current_ips, ips)

    if input(f'Would you like to update {host}? (y/n): ') != 'y':
        return

    commands = generate_juniper(ips)

    c.send_config_set(commands, config_mode_command='configure exclusive')
    c.disconnect()


def generate_config(vendor: str, ips: set, ) -> list:
    if vendor not in VENDORS:
        raise ValueError(f'Unknown vendor {vendor}')
    if vendor == VENDOR_CISCO:
        return generate_cisco(ips, '<OG-IN-ACL-NAME>', '<OG-OUT-ACL-NAME>')
    elif vendor == VENDOR_JUNIPER:
        return generate_juniper(ips)


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
    result.append('commit')
    return result
