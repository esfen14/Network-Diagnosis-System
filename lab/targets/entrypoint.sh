#!/bin/sh
# Configure services from the environment, then run them under supervisord.
#   SSH_PORT    default 22
#   HTTP_PORTS  space-separated, default "" (none)
#   HTTPS       "1" serves 443 with a self-signed certificate
#   SNMP        "1" runs snmpd on udp/161, community "public" (lab only)
set -e
SSH_PORT="${SSH_PORT:-22}"
conf=/etc/supervisor/conf.d/lab.conf
: > "$conf"

sed -i -E "s/^#?Port .*/Port $SSH_PORT/" /etc/ssh/sshd_config
grep -q '^PasswordAuthentication' /etc/ssh/sshd_config \
  && sed -i -E 's/^PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config \
  || echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config
printf '[program:sshd]\ncommand=/usr/sbin/sshd -D -e\nautorestart=true\n' >> "$conf"

rm -f /etc/nginx/sites-enabled/default
: > /etc/nginx/conf.d/lab.conf
for p in ${HTTP_PORTS:-}; do
  printf 'server { listen %s; location / { return 200 "%s http %s\\n"; add_header Content-Type text/plain; } }\n' "$p" "$(hostname)" "$p" >> /etc/nginx/conf.d/lab.conf
done
if [ "${HTTPS:-0}" = "1" ]; then
  openssl req -x509 -nodes -newkey rsa:2048 -days 30 -subj "/CN=$(hostname)" \
    -keyout /etc/ssl/private/lab.key -out /etc/ssl/certs/lab.crt 2>/dev/null
  printf 'server { listen 443 ssl; ssl_certificate /etc/ssl/certs/lab.crt; ssl_certificate_key /etc/ssl/private/lab.key; location / { return 200 "%s https\\n"; add_header Content-Type text/plain; } }\n' "$(hostname)" >> /etc/nginx/conf.d/lab.conf
fi
if [ -s /etc/nginx/conf.d/lab.conf ]; then
  printf '[program:nginx]\ncommand=/usr/sbin/nginx -g "daemon off;"\nautorestart=true\n' >> "$conf"
fi

if [ "${SNMP:-0}" = "1" ]; then
  printf 'agentaddress udp:161\nrocommunity public default\nsysName %s\n' "$(hostname)" > /etc/snmp/snmpd.conf
  printf '[program:snmpd]\ncommand=/usr/sbin/snmpd -f -Lo -C -c /etc/snmp/snmpd.conf\nautorestart=true\n' >> "$conf"
fi

exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
