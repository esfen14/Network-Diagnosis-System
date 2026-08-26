from pathlib import Path

_template_cache = {}

def _load_template(name):
    if name not in _template_cache:
        template_cache = Path(__file__).parent / "templates" / name
        _template_cache[name] = template_cache.read_text()
    return _template_cache[name]

def create_host(host):
    return _load_template("host.cfg.tpl").format(
        host_name=host["host_name"],
        alias=host["alias"],
        address=host["address"],
        contact_groups=host["contact_groups"] 
    )
    
def create_service(service, service_command):
    return _load_template("service.cfg.tpl").format(
        host_name=service["host_name"],
        service_name=service["service_name"],
        command=service_command,
        contact_groups=service["contact_groups"] 
    ) 
    
def create_contact(contact):
    return _load_template("contact.cfg.tpl").format(
        contact_name=contact["contact_name"],
        use=contact["use"],
        alias=contact["full_name"],
        email_address=contact["email_address"] 
    )

def create_contact_template(contact_template):
    return _load_template("contact_template.cfg.tpl").format(
        template_name=contact_template
    )
    
def create_hostgroup(hostgroup):
    return _load_template("hostgroup.cfg.tpl").format(
        group_name=hostgroup["group_name"],
        alias=hostgroup["alias_name"],
        members=hostgroup["member_list"] 
    )

def create_contactgroup(contactgroup):
    return _load_template("contactgroup.cfg.tpl").format(
        contactgroup_name=contactgroup["group_name"],
        alias=contactgroup["alias_name"],
        members=contactgroup["member_list"] 
    )

def create_multi_host_service(host_group_name, service_name, command, contactgroup):
    return _load_template("contactgroup.cfg.tpl").format(
        host_group_name=host_group_name,
        service_name=service_name,
        command=command,
        contact_groups=contactgroup
    )