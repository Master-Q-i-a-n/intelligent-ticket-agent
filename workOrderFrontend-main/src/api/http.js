import axios from 'axios'
import { removeSession, sessionState } from '../store/session'

const request = axios.create({
  baseURL: import.meta.env.VITE_APP_BASE_API || '/api',
  timeout: 60000
})

request.interceptors.request.use(config => {
  if (sessionState.token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${sessionState.token}`
  }
  return config
})

function handleUnauthorized() {
  removeSession()
  if (window.location.pathname !== '/login') {
    window.location.replace('/login')
  }
}

request.interceptors.response.use(
  response => {
    const body = response.data
    if (body && typeof body === 'object' && 'code' in body && body.code !== 200) {
      if (Number(body.code) === 401) {
        handleUnauthorized()
      }
      return Promise.reject(new Error(body.msg || 'Request failed'))
    }
    return body
  },
  error => {
    if (error?.response?.status === 401) {
      handleUnauthorized()
    }
    return Promise.reject(error)
  }
)

export default request
