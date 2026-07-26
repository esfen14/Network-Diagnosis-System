export type Report = {
  id: number
  linkId: string
  localInterface: string
  remoteInterface: string
  remoteDevice: string
  linkSpeed: string
  linkType: string
  discoveryMethod: string
  duplex: string
  timestamp: string
}

export const reports: Report[] = [
  {
    id: 1,
    linkId: 'LNK-001',
    localInterface: 'Gi0/0',
    remoteInterface: 'Gi0/1',
    remoteDevice: 'SW-001',
    linkSpeed: '1 Gbps',
    linkType: 'Ethernet',
    discoveryMethod: 'LLDP',
    duplex: 'Full',
    timestamp: '2026-07-26 09:15:42',
  },
  {
    id: 2,
    linkId: 'LNK-002',
    localInterface: 'Gi0/2',
    remoteInterface: 'Gi0/3',
    remoteDevice: 'RTR-001',
    linkSpeed: '10 Gbps',
    linkType: 'Fiber',
    discoveryMethod: 'CDP',
    duplex: 'Full',
    timestamp: '2026-07-26 09:16:03',
  },
  {
    id: 3,
    linkId: 'LNK-003',
    localInterface: 'Fa0/1',
    remoteInterface: 'Fa0/2',
    remoteDevice: 'AP-001',
    linkSpeed: '100 Mbps',
    linkType: 'Ethernet',
    discoveryMethod: 'LLDP',
    duplex: 'Half',
    timestamp: '2026-07-26 09:17:28',
  },
  {
    id: 4,
    linkId: 'LNK-004',
    localInterface: 'Gi1/0',
    remoteInterface: 'Gi1/1',
    remoteDevice: 'FW-001',
    linkSpeed: '1 Gbps',
    linkType: 'Ethernet',
    discoveryMethod: 'CDP',
    duplex: 'Full',
    timestamp: '2026-07-26 09:18:10',
  },
  {
    id: 5,
    linkId: 'LNK-005',
    localInterface: 'Gi0/5',
    remoteInterface: 'Gi0/7',
    remoteDevice: 'SW-002',
    linkSpeed: '1 Gbps',
    linkType: 'Ethernet',
    discoveryMethod: 'LLDP',
    duplex: 'Full',
    timestamp: '2026-07-26 09:19:41',
  },
  {
    id: 6,
    linkId: 'LNK-006',
    localInterface: 'Gi0/8',
    remoteInterface: 'Gi0/9',
    remoteDevice: 'RTR-002',
    linkSpeed: '10 Gbps',
    linkType: 'Fiber',
    discoveryMethod: 'CDP',
    duplex: 'Full',
    timestamp: '2026-07-26 09:20:15',
  },
]