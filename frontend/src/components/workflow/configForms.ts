import type { JsonObject, JsonValue } from '../../types/workflow'

const secretNames = new Set([
  'password', 'passwd', 'pwd', 'apikey', 'xapikey', 'secret', 'clientsecret',
  'accesstoken', 'refreshtoken', 'authtoken', 'xauthtoken', 'bearertoken',
  'authorization', 'cookie', 'setcookie', 'proxyauthorization', 'privatekey',
])

const managedHeaders = new Set([
  'host', 'content-length', 'transfer-encoding', 'connection', 'keep-alive',
  'proxy-connection', 'te', 'trailer', 'upgrade', 'accept-encoding',
])

export function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function normalizedKey(value: string): string {
  return value.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '')
}

function checkJson(value: unknown, depth = 0): string | null {
  if (depth > 64) return 'JSON is too deeply nested.'
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return null
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return 'JSON numbers must be finite.'
    return Number.isInteger(value) && !Number.isSafeInteger(value)
      ? 'JSON integers exceed the browser safe range. Use a string for a large identifier.' : null
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const error = checkJson(item, depth + 1)
      if (error) return error
    }
    return null
  }
  if (isJsonObject(value)) {
    for (const [key, item] of Object.entries(value)) {
      if (secretNames.has(normalizedKey(key)) && item !== null && item !== '') {
        return 'Plaintext credentials cannot be saved in node configuration.'
      }
      const error = checkJson(item, depth + 1)
      if (error) return error
    }
    return null
  }
  return 'Use only valid JSON values.'
}

export type ParsedJson = { value: JsonValue; error: null } | { value?: never; error: string }

export function parseConfigJson(text: string, objectOnly = false): ParsedJson {
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch {
    return { error: 'Invalid JSON. Check quotes, commas and brackets.' }
  }
  if (objectOnly && !isJsonObject(value)) return { error: 'Enter a JSON object.' }
  const error = checkJson(value)
  return error ? { error } : { value: value as JsonValue, error: null }
}

export function validateHeaders(value: JsonValue): string | null {
  if (!isJsonObject(value)) return 'Headers must be a JSON object with string values.'
  const seen = new Set<string>()
  let size = 0
  for (const [key, item] of Object.entries(value)) {
    const name = key.toLowerCase()
    if (
      secretNames.has(normalizedKey(key)) || normalizedKey(key) === 'token'
      || managedHeaders.has(name) || name.startsWith('proxy-')
    ) return 'Sensitive or client-managed headers cannot be saved. Remove the forbidden header.'
    if (
      typeof item !== 'string' || !/^[!#$%&'*+.^_`|~0-9A-Za-z-]+$/.test(key)
      || /[^\x20-\x7e]/.test(item)
    ) return 'Headers require valid names and single-line ASCII string values.'
    if (seen.has(name)) return 'Header names must be unique, ignoring case.'
    seen.add(name)
    size += key.length + item.length
  }
  return size > 8192 ? 'Headers exceed the 8 KiB limit.' : null
}

export function jsonText(value: JsonValue | undefined): string {
  return value === undefined ? '' : JSON.stringify(value, null, 2)
}
