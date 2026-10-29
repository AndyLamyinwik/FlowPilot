import assert from 'node:assert/strict'
import { mkdtemp, mkdir, rm, symlink, writeFile } from 'node:fs/promises'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { after, before, test } from 'node:test'
import { createAppServer, normalizeAllowedHosts } from './server.mjs'

let directory, frontend, backend, base, target
const calls = []

async function listen(server) {
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
  return `http://127.0.0.1:${server.address().port}`
}

function close(server) {
  server?.closeAllConnections()
  return server ? new Promise(resolve => server.close(resolve)) : Promise.resolve()
}

function request(url, { method = 'GET', headers = {}, body, requestPath } = {}) {
  return new Promise((resolve, reject) => {
    const outgoing = http.request(url, { method, headers, ...(requestPath ? { path: requestPath } : {}) }, response => {
      const chunks = []
      response.on('data', chunk => chunks.push(chunk))
      response.on('error', reject)
      response.on('end', () => resolve({ status: response.statusCode, headers: response.headers, body: Buffer.concat(chunks).toString() }))
    })
    outgoing.on('error', reject)
    outgoing.end(body)
  })
}

before(async () => {
  directory = await mkdtemp(path.join(os.tmpdir(), 'flowpilot-server-'))
  const dist = path.join(directory, 'dist')
  await mkdir(path.join(dist, 'assets'), { recursive: true })
  await writeFile(path.join(dist, 'index.html'), '<!doctype html><title>FlowPilot build fixture</title>')
  await writeFile(path.join(dist, 'assets', 'index-1234abcd.js'), 'export const fixture = true')
  await writeFile(path.join(dist, '.env'), 'PRIVATE_MARKER')
  await writeFile(path.join(directory, 'outside.js'), 'OUTSIDE_MARKER')
  await mkdir(path.join(directory, 'outside-assets'))
  await writeFile(path.join(directory, 'outside-assets', 'private.js'), 'OUTSIDE_MARKER')
  backend = http.createServer((incoming, response) => {
    const chunks = []
    incoming.on('data', chunk => chunks.push(chunk))
    incoming.on('end', () => {
      calls.push({ path: incoming.url, headers: incoming.headers, body: Buffer.concat(chunks).toString(), method: incoming.method })
      const finish = () => {
        response.writeHead(incoming.url.includes('/failed') ? 422 : 200, { 'Content-Type': 'application/json', 'Connection': 'keep-alive', 'X-Result': 'retained' })
        response.end(JSON.stringify(incoming.url.includes('/health') ? { status: 'ok' } : { status: 'failed', node_results: [] }))
      }
      if (incoming.url.includes('/execute')) setTimeout(finish, 80)
      else finish()
    })
  })
  target = await listen(backend)
  frontend = createAppServer({ distDir: dist, apiProxyTarget: target })
  base = await listen(frontend)
})

after(async () => {
  await close(frontend)
  await close(backend)
  await rm(directory, { recursive: true, force: true })
})

test('production SPA routes and refresh query return build HTML, without Vite source', async () => {
  for (const route of ['/', '/editor?id=workflow-id', '/home', '/index.html']) {
    const response = await request(base + route)
    assert.equal(response.status, 200)
    assert.match(response.headers['content-type'], /text\/html/)
    assert.equal(response.headers['cache-control'], 'no-cache')
    assert.match(response.body, /FlowPilot build fixture/)
    assert.doesNotMatch(response.body, /@vite|src\/main/)
  }
})

test('static assets have explicit MIME, immutable cache and working HEAD', async () => {
  const response = await request(base + '/assets/index-1234abcd.js')
  assert.equal(response.status, 200)
  assert.match(response.headers['content-type'], /text\/javascript/)
  assert.match(response.headers['cache-control'], /immutable/)
  assert.equal(response.headers['x-content-type-options'], 'nosniff')
  const head = await request(base + '/assets/index-1234abcd.js', { method: 'HEAD' })
  assert.equal(head.status, 200)
  assert.equal(head.body, '')
  assert.equal(head.headers['content-length'], String(Buffer.byteLength(response.body)))
})

test('missing resources, dev source, secret files and unknown routes are not SPA fallbacks', async () => {
  for (const route of ['/assets/missing.js', '/src/main.tsx', '/server.mjs', '/package.json', '/node_modules/vite/package.json', '/@vite/client', '/unknown']) {
    const response = await request(base + route)
    assert.equal(response.status, 404, route)
    assert.doesNotMatch(response.body, /FlowPilot build fixture|PRIVATE_MARKER|OUTSIDE_MARKER/)
  }
  for (const route of ['/.env', '/assets/../.env', '/assets/%2e%2e/.env', '/assets/%2e%2e/%2e%2e/outside.js', '/assets/..%5coutside.js', '/assets/%00.js', '/assets/%notvalid']) {
    const response = await request(base, { requestPath: route })
    assert.equal(response.status, 400, route)
    assert.doesNotMatch(response.body, /PRIVATE_MARKER|OUTSIDE_MARKER/)
  }
})

test('static root refuses symlinks resolving outside dist', async t => {
  // Directory junctions exercise realpath confinement without requiring Windows
  // developer mode/file-symlink privileges; Unix treats this as a directory link.
  try { await symlink(path.join(directory, 'outside-assets'), path.join(directory, 'dist', 'escape'), 'junction') }
  catch (error) { if (error.code === 'EPERM') { t.skip('OS does not allow symlink creation'); return } throw error }
  const response = await request(base + '/escape/private.js')
  assert.equal(response.status, 404)
  assert.doesNotMatch(response.body, /OUTSIDE_MARKER/)
})

test('static routes reject mutation methods', async () => {
  const response = await request(base + '/editor', { method: 'POST', body: 'ignored' })
  assert.equal(response.status, 405)
  assert.equal(response.headers.allow, 'GET, HEAD')
})

test('same-origin API proxy preserves path, query, body, status and safe response headers', async () => {
  const response = await request(base + '/api/workflows?limit=20', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"name":"Fixture"}' })
  assert.equal(response.status, 200)
  assert.equal(response.headers['x-result'], 'retained')
  const last = calls.at(-1)
  assert.equal(last.path, '/api/workflows?limit=20')
  assert.equal(last.method, 'POST')
  assert.equal(last.body, '{"name":"Fixture"}')
  assert.equal(last.headers.host, new URL(target).host)
  assert.equal((await request(base + '/api/failed')).status, 422)
  assert.deepEqual(JSON.parse((await request(base + '/api/health')).body), { status: 'ok' })
})

test('proxy drops client Forwarded and hop-by-hop headers and never uses them as target', async () => {
  await request(base + '/api/health', { headers: {
    Forwarded: 'host=attacker.invalid', 'X-Forwarded-Host': 'attacker.invalid',
    'X-Forwarded-For': '127.0.0.1', Connection: 'X-Injected', 'X-Injected': 'blocked',
  } })
  const last = calls.at(-1)
  for (const header of ['forwarded', 'x-forwarded-host', 'x-forwarded-for', 'x-injected']) assert.equal(last.headers[header], undefined)
  assert.equal(last.headers.host, new URL(target).host)
})

test('synchronous Execute waits for the upstream result, preserves failed and sends once', async () => {
  const count = calls.length
  const response = await request(base + '/api/workflows/id/execute', { method: 'POST' })
  assert.equal(response.status, 200)
  assert.equal(JSON.parse(response.body).status, 'failed')
  assert.equal(calls.length, count + 1)
  assert.equal(frontend.timeout, 0)
})

test('backend connection failure returns controlled 502 without target details or retry', async () => {
  const temporary = http.createServer()
  const unusedTarget = await listen(temporary)
  await close(temporary)
  const offline = createAppServer({ distDir: path.join(directory, 'dist'), apiProxyTarget: unusedTarget })
  const url = await listen(offline)
  try {
    const response = await request(url + '/api/health')
    assert.equal(response.status, 502)
    assert.deepEqual(JSON.parse(response.body), { detail: 'Backend unavailable' })
    assert.doesNotMatch(response.body, /ECONNREFUSED|127\.0\.0\.1|stack/)
  } finally { await close(offline) }
})

test('untrusted and malformed Hosts are rejected before any proxy side effect', async () => {
  const count = calls.length
  for (const host of ['attacker.invalid:5173', 'localhost.attacker.invalid', 'localhost.:5173', 'localhost:99999', 'user@localhost', '[::1].attacker.invalid']) {
    const response = await request(base + '/api/workflows/id/execute', { method: 'POST', headers: { Host: host } })
    assert.equal(response.status, 400, host)
  }
  assert.equal(calls.length, count)
  for (const host of ['localhost:5173', 'LOCALHOST:5173', '127.0.0.1:5173', '[::1]:5173', 'backend:8000']) {
    assert.equal((await request(base + '/', { headers: { Host: host } })).status, 200, host)
  }
})

test('API routing rejects absolute request targets and encoded routing confusion', async () => {
  const count = calls.length
  for (const requestPath of ['http://attacker.invalid/api/health', '//attacker.invalid/api/health', '/%61pi/health', '/api%2fhealth']) {
    assert.equal((await request(base, { requestPath })).status, 400, requestPath)
  }
  assert.equal(calls.length, count)
})

test('deployment settings require explicit hosts and a fixed credential-free HTTP origin', () => {
  assert.deepEqual(normalizeAllowedHosts(['LOCALHOST.', 'localhost', '[0:0:0:0:0:0:0:1]', '例子.測試']), ['localhost', '[::1]', 'xn--fsqu00a.xn--g6w251d'])
  assert.deepEqual(normalizeAllowedHosts(['1234', '0177.0.0.1']), ['1234', '0177.0.0.1'])
  for (const value of [[], '*', ['*'], ['*.example.com'], ['http://localhost'], ['localhost:8000'], [' user '], ['bad_host'], ['localhost%00']]) {
    assert.throws(() => normalizeAllowedHosts(value))
  }
  for (const apiProxyTarget of ['file:///etc/passwd', 'http://user:password@backend:8000', 'http://backend:8000/path', 'http://backend:8000/?key=x', 'http://backend:8000/#part']) {
    assert.throws(() => createAppServer({ apiProxyTarget }))
  }
})
