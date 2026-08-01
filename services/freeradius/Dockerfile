FROM debian:bookworm-slim

# FreeRADIUS data plane for 802.1X Lab.
# Debian packages avoid fragile upstream image layers on some hosts.
# Lab-rendered clients + auth logs live on the shared runtime volume.

ENV DEBIAN_FRONTEND=noninteractive \
    FR_DIR=/etc/freeradius/3.0 \
    RUNTIME_DIR=/etc/freeradius/dot1x-lab

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        freeradius \
        freeradius-utils \
        freeradius-postgresql \
        ca-certificates \
        openssl \
        postgresql-client \
        procps \
        make \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /etc/freeradius/dot1x-lab /etc/freeradius/dot1x-lab-templates \
        /var/run/freeradius /etc/freeradius/dot1x-lab/logs \
    && touch /etc/freeradius/dot1x-lab/clients.dot1x.conf \
    && chown -R freerad:freerad /etc/freeradius/dot1x-lab /var/run/freeradius

# Pre-generate EAP server certificates for PEAP (lab only).
WORKDIR /etc/freeradius/3.0/certs
RUN if [ -x ./bootstrap ]; then ./bootstrap; fi \
    && chmod -R g+r /etc/freeradius/3.0/certs || true

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY templates/ /etc/freeradius/dot1x-lab-templates/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 1812/udp 1813/udp

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
