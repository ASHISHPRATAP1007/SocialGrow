'use client'

import useSWR from 'swr'
import { fetcher } from '@/lib/api'

/** GET helper. Returns data (undefined while loading), error and a mutate function. Pass null path to skip. */
export function useApi(path, params, options) {
  const key = path ? (params ? [path, cleanParams(params)] : path) : null
  const { data, error, mutate, isLoading } = useSWR(key, fetcher, { revalidateOnFocus: true, ...options })
  return { data, error, mutate, isLoading }
}

function cleanParams(params) {
  const out = {}
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') out[k] = v
  return out
}
