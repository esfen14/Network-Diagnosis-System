# A small monitored server: sshd, nginx and snmpd, each switched on by
# environment variables, run under supervisord so `lab break` can stop one
# service without stopping the container.
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-server nginx snmpd snmp supervisor sudo openssl iproute2 procps curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/sshd \
    && useradd -m -s /bin/bash labadmin && echo 'labadmin:labadmin' | chpasswd \
    && echo 'labadmin ALL=(ALL) ALL' > /etc/sudoers.d/labadmin && chmod 440 /etc/sudoers.d/labadmin
COPY lab/targets/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
