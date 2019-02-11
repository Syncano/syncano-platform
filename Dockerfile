FROM madnight/docker-alpine-wkhtmltopdf:alpine-3.8
FROM python:3.6-alpine3.8

ARG EMAIL=devops@syncano.com
ENV PYTHON_EGG_CACHE=/home/syncano/.python-eggs \
    ACME_VERSION=2.7.9 \
    LE_WORKING_DIR=/acme/home \
    LE_CONFIG_HOME=/acme/config \
    CERT_HOME=/acme/certs \
    GDAL_LIBRARY_PATH=/usr/lib/libgdal.so.20 \
    GEOS_LIBRARY_PATH=/usr/lib/libgeos_c.so.1

RUN set -ex \
    && pip install --upgrade pip \
    && adduser -D -s /bin/bash syncano \
    && apk add --no-cache \
        bash \
        curl \
        supervisor \
        postgresql-client \
        make \
        # openssl support
        ca-certificates \
        openssl \
        # nginx
        nginx \
        libxml2 \
        # unzip and mksquashfs for env zip processing
        squashfs-tools \
        unzip \
        # tini to avoid zombies
        tini \
        # usermod
        shadow \
        # more correct su
        su-exec \
        # real ps
        procps \
        # pdf packages
        xvfb \
        ttf-freefont \
        fontconfig \
        dbus \
        # dependencies of wkhtmltopdf
        libgcc libstdc++ libx11 glib libxrender libxext libintl \
    \
    # Install libcrypto from edge for gdal-2.3.2r1
    && apk add --no-cache --repository http://dl-cdn.alpinelinux.org/alpine/edge/main \
        libcrypto1.1 \
    \
    # Install testing packages
    && apk add --no-cache --repository http://dl-cdn.alpinelinux.org/alpine/edge/testing \
        geos \
        gdal \
    \
    # Symlink libgeos so it gets picked up correctly
    && ln -s /usr/lib/libgeos_c.so.1 /usr/lib/libgeos_c.so \
    \
    # PDF support
    && echo $'#!/usr/bin/env sh\n\
Xvfb :0 -screen 0 1024x768x24 -ac +extension GLX +render -noreset & \n\
DISPLAY=:0.0 wkhtmltopdf-origin $@ \n\
killall Xvfb\
' > /usr/bin/wkhtmltopdf \
    && chmod +x /usr/bin/wkhtmltopdf \
    \
    # Install acme.sh
    && wget https://github.com/Neilpang/acme.sh/archive/${ACME_VERSION}.zip \
    && unzip ${ACME_VERSION}.zip \
    && cd acme.sh-${ACME_VERSION} \
    && mkdir -p ${LE_WORKING_DIR} ${LE_CONFIG_HOME} ${CERT_HOME} \
    && ./acme.sh --install --nocron --home ${LE_WORKING_DIR} --config-home ${LE_CONFIG_HOME} --cert-home ${CERT_HOME} \
        --accountemail "${EMAIL}" --accountkey "/acme/config/account.key" \
    && ln -s ${LE_WORKING_DIR}/acme.sh /usr/bin/acme.sh \
    && cd .. \
    && rm -rf ${ACME_VERSION}.zip acme.sh-${ACME_VERSION} \
    # Remove default nginx config
    && mkdir -p /run/nginx \
    && rm -rf /etc/nginx/conf.d/*

# Install python dependencies
COPY ./requirements.txt /home/syncano/app/
COPY ./modules /home/syncano/app/modules
WORKDIR /home/syncano/app
RUN set -ex \
    && apk add --no-cache --virtual .build-deps \
        linux-headers \
        build-base \
        make \
        pcre-dev \
        libffi-dev \
        musl-dev \
        postgresql-dev \
        libxml2-dev \
        libxslt-dev \
        git \
    && pip3 install --no-cache-dir -r requirements.txt modules/serializer \
    && apk del .build-deps

# Copy the application folder inside the container
COPY --chown=syncano . /home/syncano/app
RUN chown syncano:syncano /home/syncano/app

# Copy wkhtmltopdf
COPY --from=0 /bin/wkhtmltopdf /usr/bin/wkhtmltopdf-origin

# Set the default command to execute
# when creating a new container
CMD ["/home/syncano/app/run.sh"]
ENTRYPOINT ["/sbin/tini", "--"]
