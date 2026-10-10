define host {{
    host_name                       {host_name}
    alias                           {alias}
    address                         {address}
    check_command                   check-host-alive
    max_check_attempts              3
    check_interval                  {check_interval}
    checks_enabled                  1
    retain_status_information       1
    retain_nonstatus_information    1
    notification_interval           30
    notification_period             24x7
    contact_groups                  {contact_groups}
}}