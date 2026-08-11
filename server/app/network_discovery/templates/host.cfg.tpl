define host {{
    host_name                       {name}
    alias                           {alias}
    address                         {address}
    check_command                   check-host-alive
    max-check_attempts              3
    checks_enabled                  1
    failure_prediction_enable       1
    retain_status_information       1
    retain_nonstatus_information    1
    notification_interval           5
    notification_period             24x7
    contact_groups                  {contact_groups}
}}