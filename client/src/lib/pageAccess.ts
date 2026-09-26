// Which permission each page needs. A page is hidden from the sidebar and
// its URL redirects away when the user's role lacks the permission.
// null means every logged-in user can open it.
//
// Each permission is the one the page's own API routes require, so a
// visible page never loads into a wall of 403s.
export const PAGE_PERMISSIONS: Record<string, string | null> = {
  '/dashboard': 'system.dashboard',
  '/network-health': 'system.network_health',
  '/device-inventory': 'system.network_health',
  '/topology': 'system.network_health',
  '/plugins': 'plugin.view',
  '/reports': 'system.report',
  '/system-logs': 'system.logs',
  '/accounts': 'account.view',
  '/manage-roles': 'role.view',
  '/settings': null,
}

// Settings tabs beyond General (which everyone can use).
export const SETTINGS_TAB_PERMISSIONS = {
  security: 'settings.security',
  system: 'settings.system',
} as const

// Where to send a user who opens a page they can't access, in sidebar order.
const PAGE_ORDER = Object.keys(PAGE_PERMISSIONS)

export function canAccessPage(pathname: string, permissions: readonly string[]): boolean {
  const required = PAGE_PERMISSIONS[pathname]
  // Paths not listed here aren't permission-gated pages.
  if (required === undefined || required === null) return true
  return permissions.includes(required)
}

export function firstAccessiblePage(permissions: readonly string[]): string {
  return PAGE_ORDER.find((path) => canAccessPage(path, permissions)) ?? '/settings'
}
