const SESSION_KEY = 'workorder.session'

export function normalizeRole(value) {
  const role = String(value || '').toLowerCase()
  if (role === 'user' || role === 'admin') {
    return role
  }
  return 'guest'
}

export function getDefaultRouteByRole(role) {
  const normalized = normalizeRole(role)
  if (normalized === 'user') {
    return '/feedback'
  }
  if (normalized === 'admin') {
    return '/work-order'
  }
  return '/login'
}

export function readSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    return raw ? JSON.parse(raw) : null
  } catch (error) {
    return null
  }
}

export function writeSession(session) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session))
}

export function clearSession() {
  localStorage.removeItem(SESSION_KEY)
}

export function getAccessToken() {
  return readSession()?.token || ''
}

export function getCurrentRole() {
  return normalizeRole(readSession()?.user?.role)
}

export function isAuthenticated() {
  return Boolean(getAccessToken())
}
