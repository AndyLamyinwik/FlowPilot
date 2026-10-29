import { createReadStream } from 'node:fs'
import { realpath, stat } from 'node:fs/promises'
import http from 'node:http'
import https from 'node:https'
import { isIP } from 'node:net'
import path from 'node:path'
import { domainToASCII, fileURLToPath } from 'node:url'

export const DEFAULT_ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]', 'backend']
const ROOT = path.dirname(fileURLToPath(import.meta.url))
const SPA_PATHS = new Set(['/', '/index.html', '/editor', '/home'])
const MIME_TYPES = {
  '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.ico': 'image/x-icon', '.webp': 'image/webp', '.woff': 'font/woff', '.woff2': 'font/woff2',
}
const HOP_HEADERS = new Set([
  'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailer', 'transfer-encoding', 'upgrade',
])

export function normalizeAllowedHosts(values) {
  if (!Array.isArray(values) || values.length === 0) throw new Error('FLOWPILOT_ALLOWED_HOSTS must be a nonempty JSON array of exact hosts')
  return [...new Set(values.map(value => {
    if (typeof value !== 'string' || !value || value !== value.trim() || /[\/\\@?#%*]/.test(value)) {
      throw new Error('FLOWPILOT_ALLOWED_HOSTS must contain exact hosts without URLs or ports')
    }
    const host = value.startsWith('[') && value.endsWith(']') ? value.slice(1, -1) : value
    if (isIP(host) === 6) return new URL(`http://[${host}]`).hostname
    if (isIP(host) === 4) return host
    const name = host.replace(/\.+$/, '')
    // Preserve literal ASCII names: URL's IDNA helper also rewrites numeric
    // names such as "1234" as IPv4, unlike an exact hostname allowlist.
    const ascii = (/^[\x00-\x7f]+$/.test(name) ? name : domainToASCII(name)).toLowerCase()
    if (!ascii || ascii.length > 253 || ascii.split('.').some(label => !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))) {
      throw new Error('FLOWPILOT_ALLOWED_HOSTS must contain valid exact hosts')
    }
    return ascii
  }))]
}

function parseTarget(value) {
  const target = new URL(value)
  if (!['http:', 'https:'].includes(target.protocol) || target.username || target.password
    || target.pathname !== '/' || target.search || target.hash) {
    throw new Error('API_PROXY_TARGET must be an HTTP(S) origin without credentials, path or query')
  }
  return target
}

function incomingHost(request) {
  if (request.headersDistinct.host?.length !== 1) return null
  const value = request.headers.host
  if (typeof value !== 'string' || /[\s/\\@?#%]/.test(value)) return null
  const match = value.match(/^(\[[\da-f:.]+\]|[a-z\d.-]+)(?::(\d{1,5}))?$/i)
  if (!match || (match[2] && (Number(match[2]) < 1 || Number(match[2]) > 65535))) return null
  return match[1].toLowerCase()
}

function forwardHeaders(headers) {
  const blocked = new Set([...HOP_HEADERS, ...(headers.connection ?? '').split(',').map(value => value.trim().toLowerCase())])
  return Object.fromEntries(Object.entries(headers).filter(([name]) => !blocked.has(name)
    && name !== 'forwarded' && !name.startsWith('x-forwarded-')))
}

function reply(response, status, detail) {
  if (response.destroyed) return
  if (response.headersSent) { response.destroy(); return }
  response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' })
  response.end(JSON.stringify({ detail }))
}

function proxy(request, response, target) {
  // The destination comes only from deployment settings, never the request URL
  // or Forwarded headers. One request, no retry, and no short response timeout:
  // synchronous Execute can run longer than ordinary browser API requests.
  const transport = target.protocol === 'https:' ? https : http
  const upstream = transport.request(target, {
    method: request.method, path: request.url,
    headers: { ...forwardHeaders(request.headers), host: target.host },
    timeout: 0,
  }, result => {
    response.writeHead(result.statusCode ?? 502, forwardHeaders(result.headers))
    result.on('error', () => response.destroy())
    result.on('aborted', () => response.destroy())
    result.pipe(response)
  })
  upstream.on('error', () => reply(response, 502, 'Backend unavailable'))
  request.on('aborted', () => upstream.destroy())
  request.on('error', () => upstream.destroy())
  response.on('close', () => { if (!response.writableEnded) upstream.destroy() })
  request.pipe(upstream)
}

async function serveStatic(request, response, pathname, distDir) {
  if (!['GET', 'HEAD'].includes(request.method)) {
    response.setHeader('Allow', 'GET, HEAD')
    reply(response, 405, 'Method not allowed')
    return
  }
  const spa = SPA_PATHS.has(pathname)
  const extension = path.extname(pathname).toLowerCase()
  if (!spa && !Object.hasOwn(MIME_TYPES, extension)) { reply(response, 404, 'Not found'); return }
  try {
    const root = await realpath(distDir)
    const candidate = path.resolve(root, `.${spa ? '/index.html' : pathname}`)
    const file = await realpath(candidate)
    const relative = path.relative(root, file)
    if (relative.startsWith(`..${path.sep}`) || relative === '..' || path.isAbsolute(relative)) {
      reply(response, 404, 'Not found')
      return
    }
    const info = await stat(file)
    if (!info.isFile()) { reply(response, 404, 'Not found'); return }
    response.writeHead(200, {
      'Content-Type': spa ? 'text/html; charset=utf-8' : MIME_TYPES[extension],
      'Content-Length': info.size,
      'Cache-Control': !spa && /^\/assets\/[^/]+-[\w-]{8,}\.[\w]+$/.test(pathname)
        ? 'public, max-age=31536000, immutable' : 'no-cache',
      'X-Content-Type-Options': 'nosniff',
    })
    if (request.method === 'HEAD') { response.end(); return }
    createReadStream(file).on('error', () => response.destroy()).pipe(response)
  } catch (error) {
    reply(response, ['ENOENT', 'ENOTDIR', 'EACCES'].includes(error.code) ? 404 : 500, 'Static resource unavailable')
  }
}

export function createAppServer({
  distDir = path.join(ROOT, 'dist'), apiProxyTarget = 'http://127.0.0.1:8000',
  allowedHosts = DEFAULT_ALLOWED_HOSTS,
} = {}) {
  const target = parseTarget(apiProxyTarget)
  const hosts = new Set(normalizeAllowedHosts(allowedHosts))
  const server = http.createServer((request, response) => {
    response.setHeader('X-Content-Type-Options', 'nosniff')
    if (!hosts.has(incomingHost(request))) { reply(response, 400, 'Invalid host header'); return }
    const raw = request.url ?? ''
    if (!raw.startsWith('/') || raw.startsWith('//') || /[\\#\x00-\x20\x7f]/.test(raw)) {
      reply(response, 400, 'Invalid request path')
      return
    }
    let pathname
    try { pathname = decodeURIComponent(raw.split('?', 1)[0]) } catch { reply(response, 400, 'Invalid request path'); return }
    if (/[\\\x00-\x1f\x7f]/.test(pathname) || pathname.split('/').some(part => part.startsWith('.'))) {
      reply(response, 400, 'Invalid request path')
      return
    }
    if (pathname === '/api' || pathname.startsWith('/api/')) {
      // Require the same raw prefix so encoded separators cannot change routing.
      if (raw !== '/api' && !raw.startsWith('/api/') && !raw.startsWith('/api?')) { reply(response, 400, 'Invalid API path'); return }
      proxy(request, response, target)
    } else {
      void serveStatic(request, response, pathname, distDir)
    }
  })
  server.timeout = 0
  server.on('upgrade', (_request, socket) => socket.destroy())
  return server
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const port = Number(process.env.FLOWPILOT_FRONTEND_PORT ?? 5173)
    if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('FLOWPILOT_FRONTEND_PORT must be between 1 and 65535')
    const server = createAppServer({
      apiProxyTarget: process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
      allowedHosts: process.env.FLOWPILOT_ALLOWED_HOSTS ? JSON.parse(process.env.FLOWPILOT_ALLOWED_HOSTS) : DEFAULT_ALLOWED_HOSTS,
    })
    const host = process.env.FLOWPILOT_FRONTEND_HOST ?? '127.0.0.1'
    server.on('error', () => { console.error('FlowPilot frontend could not listen on the configured address'); process.exitCode = 1 })
    server.listen(port, host, () => console.info('FlowPilot production frontend listening'))
    const shutdown = () => server.close(() => { process.exitCode = 0 })
    process.once('SIGTERM', shutdown)
    process.once('SIGINT', shutdown)
  } catch {
    console.error('Invalid frontend settings. Check API_PROXY_TARGET, FLOWPILOT_ALLOWED_HOSTS and FLOWPILOT_FRONTEND_PORT')
    process.exitCode = 1
  }
}
