#!/bin/bash
DOMAIN=$1
LAST_UPDATE=$(date -Iseconds -u)+$RANDOM

# If domain directory does not exist, exit
[ ! -d $CERT_HOME/$DOMAIN ] && exit 0

# Delete domain certs and PEM
rm -rf $CERT_HOME/$DOMAIN $CERT_HOME/pem/$DOMAIN.pem

# Update last_update file so proxy gets reloaded
echo $LAST_UPDATE > $CERT_HOME/.last_update
