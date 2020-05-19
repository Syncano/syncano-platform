FROM python:3.7-alpine3.11

ARG EMAIL
ARG UID=1000
ARG GID=1000

ENV PYTHON_EGG_CACHE=/home/syncano/.python-eggs \
    ACME_VERSION=2.8.3 \
    LE_WORKING_DIR=/acme/home \
    LE_CONFIG_HOME=/acme/config \
    CERT_HOME=/acme/certs \
    GDAL_LIBRARY_PATH=/usr/lib/libgdal.so.26 \
    GEOS_LIBRARY_PATH=/usr/lib/libgeos_c.so.1

RUN set -ex \
    && pip install --upgrade pip \
    && addgroup -S -g $GID syncano \
    && adduser -S -D -G syncano -s /bin/bash -u $UID syncano \
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
        # pdf rendering
        wkhtmltopdf \
        ttf-freefont \
        # postgis dependencies
        geos \
        gdal \
        # nginx
        nginx \
    \
    # Set nginx and acme permissions
    && ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log \
    && chown syncano:syncano -R /var/lib/nginx \
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
    && rm -rf ${ACME_VERSION}.zip acme.sh-${ACME_VERSION} \
    && chown syncano:syncano -R /acme

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
RUN python manage.py collectstatic --noinput \
    && chown syncano:syncano /home/syncano/app \
    && chown syncano:syncano -R /home/syncano/app/static
USER syncano

# Set the default command to execute
# when creating a new container
CMD ["/home/syncano/app/run.sh"]
ENTRYPOINT ["/sbin/tini", "--"]
