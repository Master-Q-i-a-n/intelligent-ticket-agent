import axios from 'axios'
import { sessionState } from '../store/session'

const request = axios.create({
  baseURL: import.meta.env.VITE_APP_BASE_API || '/api',
  timeout: 15000
})

request.interceptors.request.use(config => {
  if (sessionState.token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${sessionState.token}`
  }
  return config
})

request.interceptors.response.use(
  response => {
    const body = response.data
    if (body && typeof body === 'object' && 'code' in body && body.code !== 200) {
      return Promise.reject(new Error(body.msg || 'Request failed'))
    }
    return body
  },
  error => Promise.reject(error)
)

export default request
