FROM python:3.6-alpine3.11

ARG EMAIL=devops@syncano.com
ENV PYTHON_EGG_CACHE=/home/syncano/.python-eggs \
    ACME_VERSION=2.8.3 \
    LE_WORKING_DIR=/acme/home \
    LE_CONFIG_HOME=/acme/config \
    CERT_HOME=/acme/certs \
    GDAL_LIBRARY_PATH=/usr/lib/libgdal.so.26 \
    GEOS_LIBRARY_PATH=/usr/lib/libgeos_c.so.1

RUN set -ex \
    && pip install --upgrade pip \
    && adduser -D -s /bin/bash syncano \
    && apk add --no-cache \
        bash \
        coreutils \
        curl \
        supervisor \
        postgresql-client \
        make \
        libxml2 \
        # openssl support
        ca-certificates \
        openssl \
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
        # wkhtmltopdf
        wkhtmltopdf \
        # postgis dependencies
        geos \
        gdal \
        # haproxy
        haproxy \
    \
    # Symlink libgeos so it gets picked up correctly
    && ln -s /usr/lib/libgeos_c.so.1 /usr/lib/libgeos_c.so \
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
    && rm -rf ${ACME_VERSION}.zip acme.sh-${ACME_VERSION}

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

# Set the default command to execute
# when creating a new container
CMD ["/home/syncano/app/run.sh"]
ENTRYPOINT ["/sbin/tini", "--"]
