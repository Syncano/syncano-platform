# coding=UTF8


def add_domains_to_syncano_instance(syncano_instance, domains):
    for domain in domains:
        if domain not in syncano_instance.domains:
            syncano_instance.domains.append(domain)


def remove_domains_from_syncano_instance(syncano_instance, domains):
    for domain in domains:
        if domain in syncano_instance.domains:
            syncano_instance.domains.remove(domain)
