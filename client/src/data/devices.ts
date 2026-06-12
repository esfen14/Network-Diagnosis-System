
{/* HOLDER LANG, PARA MAKITA YUNG LAYOUT */}
export type Device = {
  id: string
  hostName: string
  deviceType: string
  deviceIp: string
  osVersion: string
  router: string
  status: 'Online' | 'Offline'
}

export const devices: Device[] = [
  { id: '#D-002', hostName: 'R2', deviceType: 'Router', deviceIp: '192.168.99.2', osVersion: 'IOS-XE 17.6', router: 'R1', status: 'Online' },
  { id: '#D-003', hostName: 'R3', deviceType: 'Router', deviceIp: '192.168.99.3', osVersion: 'IOS-XE 17.3', router: 'R1', status: 'Online' },
  { id: '#D-004', hostName: 'SW1', deviceType: 'Switch', deviceIp: '192.168.99.10', osVersion: 'IOS 15.2', router: 'R1', status: 'Online' },
  { id: '#D-007', hostName: 'SRV-Web1', deviceType: 'Server', deviceIp: '192.168.99.20', osVersion: 'Ubuntu Server 22.04', router: 'R1', status: 'Online' },
  { id: '#D-008', hostName: 'SRV-DB1', deviceType: 'Server', deviceIp: '192.168.99.21', osVersion: 'CentOS 8', router: 'R1', status: 'Offline' },
  { id: '#D-009', hostName: 'PC-Admin1', deviceType: 'PC', deviceIp: '192.168.99.50', osVersion: 'Windows 11 Pro', router: 'R1', status: 'Online' },
  { id: '#D-010', hostName: 'PC-Admin2', deviceType: 'PC', deviceIp: '192.168.99.51', osVersion: 'Windows 11 Pro', router: 'R1', status: 'Online' },
  { id: '#D-011', hostName: 'PC-Admin3', deviceType: 'PC', deviceIp: '192.168.99.52', osVersion: 'Windows 11 Pro', router: 'R1', status: 'Online' },
  { id: '#D-024', hostName: 'SRV-File1', deviceType: 'Server', deviceIp: '192.168.99.22', osVersion: 'Ubuntu Server 22.04', router: 'R2', status: 'Online' },
  { id: '#D-025', hostName: 'SRV-Mail1', deviceType: 'Server', deviceIp: '192.168.99.23', osVersion: 'Ubuntu Server 22.04', router: 'R2', status: 'Online' },
]

export const routers = ['R1', 'R2', 'R3'] as const
