from pathlib import Path

_template_cache = {}

def load_template(name):
    if name not in _template_cache:
        _template_cache[name] = Path(f"templates/{name}").read_text()
    return _template_cache[name]

def create_host(host):
    return load_template("host.cfg.tpl").format(
        host_name=host["host_name"],
        alias=host["alias"],
        address=host["address"],
        contact_group=host["hostgroup"] 
    )
    
def create_service(service):
    return 0
    
def create_contact(contact):
    return 0

def create_contact_template(contact_template):
    return 0

def create_hostgroup(hostgroup):
    return 0

def create_contactgroup(contactgroup):
    return 0
    
def create_host_config(data):
    
    return 0