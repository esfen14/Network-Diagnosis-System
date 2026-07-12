import requests
from flask import current_app
import sqlalchemy as sa

NAGIOS_URL = "http://192.168.130.10/nagios/cgi-bin/statusjson.cgi"

USERNAME = "nagiosadmin"
PASSWORD = "password"

def insert_programstatus_data(data):
    return 0

def insert_host_status_data(data):
    return 0

def insert_service_status_data(data):
    return 0

def get_status():
    hostParams = {
    "query": "hostlist",
    "formatoptions": "enumerate",
    "details": "true"
        }
    response = requests.get(
    NAGIOS_URL,
    params=hostParams,
    auth=(USERNAME, PASSWORD),
    timeout=10
        )
    response.raise_for_status()

    data = response.json()
    # this gives you a JSON
    hostlist = data['data']['hostlist']
    # turns the JSON into a dict to easily be read
    for hostname, host_data in hostlist.items():
        print("hostname: " + hostname)
        print("hostdata: " + str(host_data))

        serviceParams ={
        "query": "servicelist",
        "hostname": hostname,
        "formatoptions": "enumerate",
        "details": "true"    
                }

        response = requests.get(
        NAGIOS_URL,
        params=serviceParams,
        auth=(USERNAME, PASSWORD),
        timeout=10
                )
        data = response.json()

        #this this gives you a JSON
        servicelist = data['data']['servicelist'].get(hostname, {})

        # turns the JSON into a dict to easily be read
        for service, service_data in servicelist.items():
            print(service)
            print(service_data)

get_status()