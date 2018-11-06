#!/bin/bash
set -e

DOMAIN=$1
LAST_UPDATE=$(date -Iseconds -u)+$RANDOM

acme.sh \
    --renew \
    -d $DOMAIN \
    --renew-hook \
        "acme.sh \
        --install-cert \
        -d $DOMAIN \
        --reloadcmd \
            'cat \$CERT_KEY_PATH \$CERT_FULLCHAIN_PATH > $CERT_HOME/pem/$DOMAIN.pem && \
            echo $LAST_UPDATE > $CERT_HOME/.last_update'"
