from ipaddress import IPv4Network

VENDOR_JUNIPER = 'juniper'
VENDOR_CISCO = 'cisco'

VENDORS = {VENDOR_JUNIPER, VENDOR_CISCO}


def generate_config(vendor: str, ips: list) -> str:
    if vendor not in VENDORS:
        raise ValueError(f'Unknown vendor {vendor}')
    if vendor == VENDOR_CISCO:
        return generate_cisco(ips)
    elif vendor == VENDOR_JUNIPER:
        return generate_juniper(ips)


def generate_cisco(ips: list) -> str:
    result = []
    for direction in ('FROM', 'TO'):
        result.append(f'ip access-list extended {direction}-OPEN-GARDEN')
        for ip in ips:
            if '/' in ip:
                net = IPv4Network(ip)
                result.append(f'permit ip {net.network_address} {net.hostmask} any')
            else:
                result.append(f'permit ip host {ip} any')
    return '\n'.join(result)


def generate_juniper(ips: list) -> str:
    result = []
    for ip in ips:
        if '/' not in ip:
            ip += '/32'
        result.append(
            f'set groups rdr-nomoney-routes routing-instances <*> routing-options static route {ip} next-table inet.0'
        )
    return '\n'.join(result)
