FROM debian:bookworm-slim

# Phase 0: stock FreeRADIUS from Debian packages.
# Avoids freeradius/freeradius-server image layers that break on some
# containerd/overlayfs hosts (whiteout conversion failures).
# Lab-rendered config is mounted at /etc/freeradius/dot1x-lab and will be
# included from sites in Phase 1.

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        freeradius \
        freeradius-utils \
        ca-certificates \
        procps \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /etc/freeradius/dot1x-lab /etc/freeradius/dot1x-lab-templates

EXPOSE 1812/udp 1813/udp

# Foreground mode so the container stays up under Compose.
CMD ["freeradius", "-f"]
