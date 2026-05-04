import { reactive } from 'vue'
import { clearSession, getCurrentRole, isAuthenticated, readSession, writeSession } from '../utils/auth'

const stored = readSession()

export const sessionState = reactive({
  token: stored?.token || '',
  user: stored?.user || null
})

export function restoreSession() {
  const session = readSession()
  sessionState.token = session?.token || ''
  sessionState.user = session?.user || null
  return sessionState
}

export function setSession(session) {
  sessionState.token = session?.token || ''
  sessionState.user = session?.user || null
  writeSession(sessionState.token ? session : null)
}

export function updateSessionUser(user) {
  if (!sessionState.token) {
    return
  }
  sessionState.user = user
  writeSession({
    token: sessionState.token,
    user
  })
}

export function removeSession() {
  sessionState.token = ''
  sessionState.user = null
  clearSession()
}

export function hasSession() {
  return isAuthenticated()
}

export function getSessionRole() {
  return getCurrentRole()
}
