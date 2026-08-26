define service {{
    use                         generic-service
    hostgroup_name              {host_group_name}
    service_description         {service_name}
    check_command               {command} 
    contact_groups              {contact_groups}
}}