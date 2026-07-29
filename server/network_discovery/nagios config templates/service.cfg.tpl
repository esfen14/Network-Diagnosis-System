define service{
    host_name                   {host_name}
    service_description         {service_name}
    check_command               {command} 
    max_check_attempts          3
    check_interval              5
    retry_interval              1
    check_period                24x7
    contact_group               {contact_group}
}