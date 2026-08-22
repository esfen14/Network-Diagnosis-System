export const logs = [
  {
    id: 1,
    category: 'activity',
    type: 'account',
    title: 'Account Created',
    user: 'Admin Ella',
    description: 'created a new account.',
    timestamp: '2026-01-20 10:45 AM',
    tagId: 'AC-1023',
  },

  {
    id: 2,
    category: 'configurationChange',
    type: 'configuration',
    title: 'Configuration Updated',
    user: 'Admin John',
    description: 'changed system configuration.',
    timestamp: '2026-01-18 02:11 PM',
    tagId: 'CC-5567',
  },

  {
    id: 3,
    category: 'networkDiscovery',
    type: 'network',
    title: 'Network Discovered',
    user: 'System',
    description: 'discovered a new network device.',
    timestamp: '2026-01-20 09:12 AM',
    tagId: 'ND-8872',
  },

  {
    id: 4,
    category: 'ncpaDeployment',
    type: 'deployment',
    title: 'NCPA Deployed',
    user: 'System',
    description: 'deployed NCPA to a monitored device.',
    timestamp: '2026-01-19 08:30 PM',
    tagId: 'NP-3321',
  },

  {
    id: 5,
    category: 'exportLog',
    type: 'export',
    title: 'System Logs Exported',
    user: 'Admin Ella',
    description: 'exported system logs.',
    timestamp: '2026-01-20 11:30 AM',
    tagId: 'EX-1045',
  },

  {
    id: 6,
    category: 'exportLog',
    type: 'export',
    title: 'System Logs Exported',
    user: 'Admin John',
    description: 'exported system logs.',
    timestamp: '2026-01-19 04:15 PM',
    tagId: 'EX-1046',
  },
] as const