#!/usr/bin/env python
import iptc
from docker import Client

SCRIPT_IMAGE_NAME = 'quay.io/syncano/script-docker-image'
ISOLATED_SUBNETS = ('10.0.0.0/16', '172.20.0.0/16')


def get_main_container_id(client):
    script_image_id = None
    for image in client.images():
        if image['RepoTags'][0].startswith(SCRIPT_IMAGE_NAME):
            script_image_id = image['Id']
            break

    if script_image_id is None:
        return

    for container in client.containers():
        if not (container['Image'] == script_image_id or
                container['Image'].startswith(SCRIPT_IMAGE_NAME)):
            return container['Id']


def super_chain(ip):
    # Check if ISOLATION chain exists and delete it with all rules
    table = iptc.Table(iptc.Table.FILTER)
    rule = iptc.Rule()

    if table.is_chain('ISOLATION'):
        table.flush_entries('ISOLATION')
        chain = iptc.Chain(iptc.Table(iptc.Table.FILTER), 'FORWARD')
        for subnet in ISOLATED_SUBNETS:
            rule.src = '0.0.0.0/0'
            rule.dst = subnet
            rule.target = rule.create_target('ISOLATION')
            try:
                chain.delete_rule(rule)
            except iptc.ip4tc.IPTCError:
                pass

        chain_isolation = iptc.Chain(table, 'ISOLATION')
        chain_isolation.flush()
    else:
        chain_isolation = table.create_chain('ISOLATION')

    # Insert rules to FORWARD chain to jump traffic
    chain_forward = iptc.Chain(table, 'FORWARD')

    for subnet in ISOLATED_SUBNETS:
        rule.src = '{0}/255.255.255.255'.format(ip)
        rule.dst = subnet
        rule.target = rule.create_target('ACCEPT')
        chain_isolation.insert_rule(rule)

        rule.src = '0.0.0.0/0'
        rule.dst = subnet
        rule.target = rule.create_target('DROP')
        chain_isolation.append_rule(rule)

        rule.dst = subnet
        rule.src = '0.0.0.0/0'
        rule.target = rule.create_target('ISOLATION')
        chain_forward.insert_rule(rule)


if __name__ == '__main__':
    c = Client(base_url='unix://var/run/docker.sock', version='auto')
    main_id = get_main_container_id(c)

    if main_id is not None:
        container_id = c.inspect_container(main_id)
        ip = c.inspect_container(container_id)['NetworkSettings']['IPAddress']
        super_chain(ip)
