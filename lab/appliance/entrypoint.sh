#!/bin/sh
# First start: copy the app in, build the databases and seed development data.
# Later starts of the same container skip the seeding.
set -e
mkdir -p /etc/pinpoint /var/run/apache2
cp /opt/lab/pinpoint.env /etc/pinpoint/pinpoint.env
chmod 644 /etc/pinpoint/pinpoint.env

pp-sync --no-restart

if [ ! -f /var/lib/pinpoint-lab-initialized ]; then
  echo "[lab] first start: creating databases and seeding development data"
  su pinpoint -s /bin/sh -c '
    set -e
    set -a; . /etc/pinpoint/pinpoint.env; set +a
    cd /opt/pinpoint/Network-Diagnosis-System/server
    /opt/pinpoint/venv/bin/flask db upgrade
    /opt/pinpoint/venv/bin/flask seed
  '
  touch /var/lib/pinpoint-lab-initialized
fi

# Lab-only time acceleration: a Nagios "minute" is 10 seconds and the first
# checks are not staggered, so QA sees results in about a minute instead of
# several. A real appliance keeps the stock values.
sed -i -E 's/^interval_length=.*/interval_length=10/; s/^(host|service)_inter_check_delay_method=.*/\1_inter_check_delay_method=n/' \
  /usr/local/nagios/etc/nagios.cfg

exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
