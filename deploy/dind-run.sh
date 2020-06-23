#!/bin/sh
set -e

rm -rf /var/run/docker.*

# Setup iptables
if [ "${SETUP_FILTERING:-1}" = "1" ]; then
    if iptables -t nat -n --list CODEBOX > /dev/null 2>&1; then
        # Flush chain if it already exists
        iptables -t nat -F CODEBOX
    else
        # Create otherwise
        iptables -t nat -N CODEBOX
    fi
    # Add forwarding
    iptables -t nat -C PREROUTING -j CODEBOX 2>&1 || iptables -t nat -I PREROUTING -j CODEBOX

    # Setup filtering
    IFS=','
    if [ -n "${DOCKER_WHITELIST}" ]; then
        for DEST in $DOCKER_WHITELIST; do
            iptables -t nat -A CODEBOX -s 172.25.0.0/16 -d "${DEST}" -p tcp -m multiport --dports 80,443 -j RETURN
        done
    fi

    iptables -t nat -A CODEBOX -s 172.25.0.0/16 -d 172.16.0.0/12 -j KUBE-MARK-DROP
    iptables -t nat -A CODEBOX -s 172.25.0.0/16 -d 192.168.0.0/16 -j KUBE-MARK-DROP
    iptables -t nat -A CODEBOX -s 172.25.0.0/16 -d 10.0.0.0/8 -j KUBE-MARK-DROP
    iptables -t nat -A CODEBOX -s 172.25.0.0/16 -d 100.64.0.0/10 -j KUBE-MARK-DROP
    iptables -C FORWARD -j KUBE-FIREWALL 2>&1 || iptables -I FORWARD -j KUBE-FIREWALL
fi

exec dockerd \
    -H unix:///var/run/docker.sock \
    --log-level=error \
    --storage-driver=overlay2 \
    --iptables="${IPTABLES:-0}"
