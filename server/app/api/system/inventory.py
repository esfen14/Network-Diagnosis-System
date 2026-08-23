from flask_login import login_required, current_user
from app import app, db
import sqlalchemy as sa
from flask import request, current_app
from app.api.helper.database_access.permissions import require_permission
from app.api.helper import success, error
from app.system_models import \
NetworkDiscovery,\
Open_TCP_Services, \
Open_UDP_Services
from app.history_models import \
HostStatus

from app.api.system import system_bp


@system_bp.get('/inventory')
@login_required
@require_permission("system.inventory")
def query_system_devices():
    try:
        page = request.args.get("page", default=1, type=int)
        per_page = request.args.get("per_page", default=10, type=int)
        sort_by = request.args.get("sort_by", default="hostname", type=str)
        order = request.args.get("order", default="asc", type=str)
        search = request.args.get("search", default="", type=str)

        if page < 1:
            return error("Page must be greater than 0", 400)

        if per_page < 1 or per_page > 100:
            return error("per_page must be between 1 and 100", 400)

        allowed_sorts = {
            "id": NetworkDiscovery.NetDiscoveryID,
            "hostname": NetworkDiscovery.Hostname,
            "ip_address": NetworkDiscovery.IP_Address,
            "network": NetworkDiscovery.Network,
            "mac_address": NetworkDiscovery.MAC_Address,
            "os_type": NetworkDiscovery.OS_Type,
            "device_type": NetworkDiscovery.Device_Type,
            "scanned_at": NetworkDiscovery.Scanned_At,
        }

        sort_column = allowed_sorts.get(sort_by)

        if sort_column is None:
            return error("Invalid sort field", 400)

        query = sa.select(NetworkDiscovery)

        if order == "asc":
            query = query.order_by(sort_column.asc())
        elif order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            return error("Invalid order.", 400)

        if search:
            search_pattern = f"%{search}%"

            query = query.where(
                sa.or_(
                    NetworkDiscovery.Hostname.ilike(search_pattern),
                    NetworkDiscovery.IP_Address.ilike(search_pattern),
                    NetworkDiscovery.Network.ilike(search_pattern),
                    NetworkDiscovery.MAC_Address.ilike(search_pattern),
                    NetworkDiscovery.OS_Type.ilike(search_pattern),
                    NetworkDiscovery.Device_Type.ilike(search_pattern),
                )
            )

        devices = db.paginate(
            query,
            page=page,
            per_page=per_page,
            error_out=False
        )

        items = []

        for device in devices.items:

            # Get the latest Nagios host status
            host_status = db.session.scalars(
                sa.select(HostStatus)
                .where(HostStatus.Hostname == device.Hostname)
                .order_by(
                    HostStatus.Timestamp.desc()
                )
                .limit(1)
            ).first()

            items.append({
                "id": device.NetDiscoveryID,
                "hostname": device.Hostname,
                "ip_address": device.IP_Address,
                "network": device.Network,
                "mac_address": device.MAC_Address,
                "os_type": device.OS_Type,
                "device_type": device.Device_Type,
                "ncpa_eligible": device.NCPA_Eligible,
                "include_in_scanning": device.Include_Device_In_Scanning,
                "scanned_at": (
                    device.Scanned_At.isoformat()
                    if device.Scanned_At is not None
                    else None
                ),
                "host_status": (
                    host_status.Current_State.value
                    if host_status is not None
                    else None
                )
            })

        return success({
            "items": items,
            "page": devices.page,
            "per_page": devices.per_page,
            "pages": devices.pages,
            "total": devices.total,
            "has_next": devices.has_next,
            "has_prev": devices.has_prev
        })

    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while querying system devices."
        )
        return error("An unexpected error occurred.", 500)


@system_bp.get('/inventory/<int:device_id>/ports/tcp')
@login_required
@require_permission("system.inventory")
def device_tcp_ports(device_id):
    try:
        device = db.session.get(NetworkDiscovery, device_id)

        if device is None:
            return error("Device not found.", 404)

        query = (
            sa.select(Open_TCP_Services)
            .where(Open_TCP_Services.NetDiscoveryID == device_id)
            .order_by(Open_TCP_Services.Port_Number.asc())
        )

        ports = db.session.scalars(query).all()

        port_list = []

        for port in ports:
            port_list.append({
                "id": port.OpenPortID,
                "port": port.Port_Number,
                "service": port.Service_Name
            })

        return success({
            "device_id": device_id,
            "protocol": "TCP",
            "ports": port_list
        })

    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while querying TCP ports."
        )
        return error("An unexpected error occurred.", 500)


@system_bp.get('/inventory/<int:device_id>/ports/udp')
@login_required
@require_permission("system.inventory")
def device_udp_ports(device_id):
    try:
        device = db.session.get(NetworkDiscovery, device_id)

        if device is None:
            return error("Device not found.", 404)

        query = (
            sa.select(Open_UDP_Services)
            .where(Open_UDP_Services.NetDiscoveryID == device_id)
            .order_by(Open_UDP_Services.Port_Number.asc())
        )

        ports = db.session.scalars(query).all()

        port_list = []

        for port in ports:
            port_list.append({
                "id": port.OpenPortID,
                "port": port.Port_Number,
                "service": port.Service_Name
            })

        return success({
            "device_id": device_id,
            "protocol": "UDP",
            "ports": port_list
        })

    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while querying UDP ports."
        )
        return error("An unexpected error occurred.", 500)
