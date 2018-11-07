#!/bin/bash
DOMAIN=$1
LAST_UPDATE=$(date -Iseconds -u)+$RANDOM

acme.sh \
    --issue \
    -d $DOMAIN  \
    --stateless

RETCODE=$?

if [ "$RETCODE" -ne 0 ] && [ "$RETCODE" -ne 2 ]; then
    exit $RETCODE
fi

# Install PEM and update last_update file so proxy gets reloaded
acme.sh \
    --install-cert \
    -d $DOMAIN \
    --reloadcmd \
        "cat \$CERT_KEY_PATH \$CERT_FULLCHAIN_PATH > $CERT_HOME/pem/$DOMAIN.pem && \
         echo $LAST_UPDATE > $CERT_HOME/.last_update"
