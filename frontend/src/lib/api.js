'use client'

import axios from 'axios'
import { mutate } from 'swr'

const TOKEN_KEY = 'sg_token'
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')

export const getToken = () => {
  if (typeof window === 'undefined') return null
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export const setToken = (token) => {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage blocked */
  }
}

export const api = axios.create({ baseURL: `${API_URL}/api/v1`, timeout: 120000 })

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error?.response?.status === 401 && getToken()) {
      setToken(null)
      if (typeof window !== 'undefined' && window.location.pathname !== '/') window.location.href = '/'
    }
    return Promise.reject(error)
  },
)

/** SWR fetcher: key is [path, params] or path */
export const fetcher = async (key) => {
  const [path, params] = Array.isArray(key) ? key : [key, undefined]
  const res = await api.get(path, { params })
  return res.data
}

/** Re-fetch every SWR query (used after any change, like Convex live updates). */
export const refreshAll = () => mutate(() => true)

export function signOut() {
  setToken(null)
  mutate(() => true, undefined, { revalidate: false })
  window.location.href = '/'
}
