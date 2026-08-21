export type Plugin = {
  id: number
  name: string
  category: string
  type: 'Service' | 'System' | 'Network'
  description: string
  status: 'Available' | 'Running'
}

export const availablePlugins: Plugin[] = [
  {
    id: 1,
    name: 'check_http',
    category: 'Web',
    type: 'Service',
    description: 'Checks web server status',
    status: 'Available',
  },
  {
    id: 2,
    name: 'check_https',
    category: 'Web',
    type: 'Service',
    description: 'Checks secure web services',
    status: 'Available',
  },
  {
    id: 3,
    name: 'check_telnet',
    category: 'Remote access',
    type: 'Network',
    description: 'Checks Telnet access',
    status: 'Available',
  },
  {
    id: 4,
    name: 'check_pop',
    category: 'Email',
    type: 'Service',
    description: 'Checks POP3 service',
    status: 'Available',
  },
  {
    id: 5,
    name: 'check_imap',
    category: 'Email',
    type: 'Service',
    description: 'Checks IMAP service',
    status: 'Available',
  },
  {
    id: 6,
    name: 'check_ftp',
    category: 'File transfer',
    type: 'System',
    description: 'Monitors FTP service',
    status: 'Available',
  },
  {
    id: 7,
    name: 'check_nt',
    category: 'Windows',
    type: 'System',
    description: 'Checks Windows-based services',
    status: 'Available',
  },
  {
    id: 8,
    name: 'check_ldap',
    category: 'Directory',
    type: 'System',
    description: 'Monitors directory services',
    status: 'Available',
  },
]

export const installedPlugins: Plugin[] = [
  {
    id: 101,
    name: 'check_ping',
    category: 'Network',
    type: 'System',
    description: 'Monitors host status and latency',
    status: 'Running',
  },
  {
    id: 102,
    name: 'check_load',
    category: 'System',
    type: 'System',
    description: 'Monitors CPU usage and load',
    status: 'Running',
  },
  {
    id: 103,
    name: 'check_disk',
    category: 'System',
    type: 'System',
    description: 'Monitors disk usage',
    status: 'Running',
  },
  {
    id: 104,
    name: 'check_mem',
    category: 'System',
    type: 'System',
    description: 'Monitors RAM usage',
    status: 'Running',
  },
  {
    id: 105,
    name: 'check_procs',
    category: 'System',
    type: 'System',
    description: 'Monitors running processes',
    status: 'Running',
  },
  {
    id: 106,
    name: 'check_users',
    category: 'System',
    type: 'System',
    description: 'Monitors logged-in users',
    status: 'Running',
  },
  {
    id: 107,
    name: 'check_mrtgtraf',
    category: 'Network',
    type: 'System',
    description: 'Bandwidth monitoring via MRTG',
    status: 'Running',
  },
  {
    id: 108,
    name: 'check_netstat',
    category: 'Network',
    type: 'System',
    description: 'Monitors active network connections',
    status: 'Running',
  },
]