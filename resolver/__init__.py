from typing import Iterable

from nslookup import Nslookup
from tqdm import tqdm


def resolve_domain(domain: str) -> list:
    dns = ["1.1.1.1"]
    dns_query = Nslookup(dns_servers=dns, verbose=False, tcp=False)
    resolved_ips = dns_query.dns_lookup(domain)
    return resolved_ips.answer


def resolve_domains(domains: Iterable) -> list:
    resolved_ips = set()
    for domain in tqdm(domains):
        resolved_ips.update(resolve_domain(domain))
    return list(resolved_ips)
