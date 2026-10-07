# Pinpoint "appliance-lite": Ubuntu 22.04 (the installer's OS) with Nagios Core
# 4.5.11 + plugins 2.4.12 built from source, Apache on :8081, and the Pinpoint
# backend under Gunicorn. No systemd: supervisord runs the processes and small
# shims stand in for `sudo`, `systemctl` and `nmap-sudo`.
#
# Build context is the repository root (see lab/compose.yaml).
FROM ubuntu:22.04

ARG NAGIOS_VERSION=4.5.11
ARG PLUGINS_VERSION=2.4.12
ARG PYTHON_VERSION=3.14
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential autoconf gettext libssl-dev libgd-dev unzip wget curl ca-certificates \
      apache2 apache2-utils iputils-ping dnsutils snmp libnet-snmp-perl nmap \
      rsync supervisor procps openssh-client sqlite3 git \
    && rm -rf /var/lib/apt/lists/*

# ---- Nagios Core (same version and steps as the installer) ----
RUN cd /usr/local/src \
 && wget -q https://github.com/NagiosEnterprises/nagioscore/releases/download/nagios-${NAGIOS_VERSION}/nagios-${NAGIOS_VERSION}.tar.gz \
 && tar xzf nagios-${NAGIOS_VERSION}.tar.gz && cd nagios-${NAGIOS_VERSION} \
 && ./configure --with-httpd-conf=/etc/apache2/sites-enabled >/dev/null \
 && make all >/dev/null \
 && make install-groups-users && usermod -a -G nagios www-data \
 && make install >/dev/null && make install-commandmode >/dev/null \
 && make install-config >/dev/null && make install-webconf >/dev/null

RUN cd /usr/local/src \
 && wget -q https://github.com/nagios-plugins/nagios-plugins/releases/download/release-${PLUGINS_VERSION}/nagios-plugins-${PLUGINS_VERSION}.tar.gz \
 && tar xzf nagios-plugins-${PLUGINS_VERSION}.tar.gz && cd nagios-plugins-${PLUGINS_VERSION} \
 && ./configure --with-nagios-user=nagios --with-nagios-group=nagios >/dev/null \
 && make >/dev/null && make install >/dev/null

# Nginx fronts Gunicorn on :80, like the installer (added after the slow Nagios
# layers so it does not invalidate their cache).
RUN apt-get update && apt-get install -y --no-install-recommends nginx \
 && rm -rf /var/lib/apt/lists/* /etc/nginx/sites-enabled/default
COPY lab/appliance/nginx-pinpoint.conf /etc/nginx/conf.d/pinpoint.conf

# ---- Python (uv, like the installer) and the backend's dependencies ----
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin INSTALLER_NO_MODIFY_PATH=1 sh \
 && uv python install ${PYTHON_VERSION} \
 && uv venv --python ${PYTHON_VERSION} /opt/pinpoint/venv
COPY server/requirements.txt /tmp/requirements.txt
RUN uv pip install --python /opt/pinpoint/venv/bin/python -r /tmp/requirements.txt "gunicorn>=25.1"

# ---- Apache on :8081, Nagios accounts and config, the pinpoint user ----
RUN useradd -m -s /bin/bash pinpoint && usermod -aG nagios pinpoint \
 && a2enmod cgi authn_file auth_basic authz_core authz_user >/dev/null \
 && echo "Listen 127.0.0.1:8081" > /etc/apache2/ports.conf \
 && a2dissite 000-default >/dev/null 2>&1 || true \
 && echo "ServerName localhost" > /etc/apache2/conf-available/servername.conf && a2enconf servername >/dev/null \
 && htpasswd -bc /usr/local/nagios/etc/htpasswd.users nagiosadmin lab-admin-pass \
 && htpasswd -b  /usr/local/nagios/etc/htpasswd.users pinpoint-api lab-api-pass \
 && sed -i -E 's/^(authorized_for_[a-z_]+=.*nagiosadmin)\s*$/\1,pinpoint-api/' /usr/local/nagios/etc/cgi.cfg \
 && echo "# Managed by the Pinpoint web interface." > /usr/local/nagios/etc/objects/hosts.cfg \
 && chown pinpoint:nagios /usr/local/nagios/etc/objects/hosts.cfg && chmod 664 /usr/local/nagios/etc/objects/hosts.cfg \
 && printf '\n# Pinpoint: hosts found by Network Discovery.\ncfg_file=/usr/local/nagios/etc/objects/hosts.cfg\n' >> /usr/local/nagios/etc/nagios.cfg \
 && chown -R nagios:nagios /usr/local/nagios/var

COPY lab/appliance/shims/sudo lab/appliance/shims/systemctl lab/appliance/shims/nmap-sudo /usr/local/bin/
COPY lab/appliance/pp-sync lab/appliance/entrypoint.sh /usr/local/bin/
COPY lab/appliance/supervisord.conf /etc/supervisor/supervisord.conf
COPY lab/appliance/pinpoint.env /opt/lab/pinpoint.env
RUN chmod 755 /usr/local/bin/sudo /usr/local/bin/systemctl /usr/local/bin/nmap-sudo /usr/local/bin/pp-sync /usr/local/bin/entrypoint.sh \
 && setcap cap_net_raw,cap_net_admin+eip "$(command -v nmap)" \
 && mkdir -p /opt/pinpoint/Network-Diagnosis-System/server && chown -R pinpoint:pinpoint /opt/pinpoint/Network-Diagnosis-System

EXPOSE 80
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
