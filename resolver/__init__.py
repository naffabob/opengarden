from typing import Iterable

from dns import resolver, exception
from tqdm import tqdm


class DNSConnectionError(Exception):
    """ For bad DNS connection """


class DNSResolveError(Exception):
    """ No domain name in answer from DNS """


def resolve_domain(domain: str) -> list:
    try:
        dns_resolver = resolver.Resolver()
    except resolver.NoResolverConfiguration:
        raise DNSConnectionError from None

    try:
        dns_answer = dns_resolver.resolve(domain)

    except (
            resolver.NXDOMAIN,  # The DNS query name does not exist.
            resolver.NoAnswer,  # The DNS response does not contain an answer to the question.
    ):
        raise DNSResolveError from None

    except (
            resolver.NoNameservers, # All nameservers failed to answer the query.
            exception.DNSException,
    ):
        raise DNSConnectionError from None

    resolved_ips = [x.address for x in dns_answer]
    return resolved_ips


def resolve_domains(domains: Iterable) -> (list, list):
    resolved_ips = set()
    unresolved_domains = set()

    for domain in tqdm(domains):
        ips = resolve_domain(domain)
        if ips:
            resolved_ips.update(ips)
        unresolved_domains.add(domain)
    return list(resolved_ips), list(unresolved_domains)
