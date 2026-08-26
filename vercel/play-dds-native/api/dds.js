'use strict';

const crypto = require('crypto');
const fs = require('fs');
const zlib = require('zlib');
const { spawn } = require('child_process');

const DAEMON_B64_URL = 'https://raw.githubusercontent.com/CapGui13/PONS-DDS-BUILD/77c1e1d9ac6efb7cdd6bd1ddc2eba31c5d5db555/r86/public/r86_dds_daemon.gz.b64';
const RELEASE = 'R86-NATIVE-VERCEL';
const ENGINE = 'DDS-2.9.1-native';
const THREADS = 2;
const BATCH_SIZE = 24;
const MAX_ITEMS = 24;
const MAX_PBN_LENGTH = 180;
const RESPONSE_TIMEOUT_MS = 30000;
const START_TIMEOUT_MS = 5000;
const BIN_SHA256 = '7148b3ee4ecd19b3a9b5205b7a6c23ccb2f42735f80a889e7c95a68af851943a';
const BIN_GZ_SHA256 = '2b9fb6f8a4009fb8d4ecf79991896d302a590f82093c0aa9190cc7f6675beb5c';
const BIN_PATH = `/tmp/play-r86-dds-${BIN_SHA256.slice(0, 12)}`;
const SELFTEST_PBN = 'N:AT62.J73.Q84.K95 K95.AT62.J73.Q84 Q84.K95.AT62.J73 J73.Q84.K95.AT62';
const SELFTEST_CANONICAL = '6,6,6,6,7,7,5,5,5,5,7,7,7,7,5,5,5,5,7,7';

const DEFAULT_ALLOWED_ORIGINS = ['https://capgui13.github.io'];
const EXTRA_ALLOWED_ORIGINS = String(process.env.BRIDGE_ALLOWED_ORIGINS || '')
  .split(',').map(s => s.trim()).filter(Boolean);
const ALLOWED_ORIGINS = new Set([...DEFAULT_ALLOWED_ORIGINS, ...EXTRA_ALLOWED_ORIGINS]);

const RATE_WINDOW_MS = 60_000;
const RATE_DEALS_PER_CLIENT = 240;
const RATE_DEALS_GLOBAL = 3000;
const RATE_KEY = '__PLAY_R86_NATIVE_DDS_RATE__';
const rateState = globalThis[RATE_KEY] || (globalThis[RATE_KEY] = {
  windowStart: Date.now(), globalCount: 0, clients: new Map()
});

function sha256(buf) { return crypto.createHash('sha256').update(buf).digest('hex'); }

async function ensureBinary() {
  try {
    const current = fs.readFileSync(BIN_PATH);
    if (sha256(current) === BIN_SHA256) {
      fs.chmodSync(BIN_PATH, 0o755);
      return BIN_PATH;
    }
  } catch (_) {}

  const resp = await fetch(DAEMON_B64_URL, { cache: 'no-store' });
  if (!resp.ok) throw new Error(`native-dds-download-http-${resp.status}`);
  const gz = Buffer.from((await resp.text()).trim(), 'base64');
  if (sha256(gz) !== BIN_GZ_SHA256) throw new Error('native-dds-gzip-sha-mismatch');
  const raw = zlib.gunzipSync(gz);
  if (sha256(raw) !== BIN_SHA256) throw new Error('native-dds-binary-sha-mismatch');

  const tmp = `${BIN_PATH}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, raw, { mode: 0o755 });
  fs.renameSync(tmp, BIN_PATH);
  fs.chmodSync(BIN_PATH, 0o755);
  return BIN_PATH;
}

class LineReader {
  constructor(stream) {
    this.buffer = '';
    this.lines = [];
    this.waiters = [];
    this.closedError = null;
    stream.setEncoding('utf8');
    stream.on('data', chunk => this._push(chunk));
    stream.on('end', () => this._close(new Error('dds-stdout-ended')));
    stream.on('error', err => this._close(err));
  }
  _push(chunk) {
    this.buffer += chunk;
    while (true) {
      const i = this.buffer.indexOf('\n');
      if (i < 0) break;
      let line = this.buffer.slice(0, i);
      this.buffer = this.buffer.slice(i + 1);
      if (line.endsWith('\r')) line = line.slice(0, -1);
      const waiter = this.waiters.shift();
      if (waiter) waiter.resolve(line);
      else this.lines.push(line);
    }
  }
  _close(err) {
    if (this.closedError) return;
    this.closedError = err || new Error('dds-reader-closed');
    for (const waiter of this.waiters.splice(0)) waiter.reject(this.closedError);
  }
  readLine(timeoutMs) {
    if (this.lines.length) return Promise.resolve(this.lines.shift());
    if (this.closedError) return Promise.reject(this.closedError);
    return new Promise((resolve, reject) => {
      const waiter = { resolve: null, reject: null };
      let timer = null;
      const cleanup = () => { if (timer) clearTimeout(timer); };
      waiter.resolve = line => { cleanup(); resolve(line); };
      waiter.reject = err => { cleanup(); reject(err); };
      this.waiters.push(waiter);
      timer = setTimeout(() => {
        const idx = this.waiters.indexOf(waiter);
        if (idx >= 0) this.waiters.splice(idx, 1);
        reject(new Error('dds-response-timeout'));
      }, timeoutMs);
    });
  }
}

function decodeCanonical(line) {
  const vals = String(line).split(',').map(Number);
  if (vals.length !== 20 || vals.some(v => !Number.isInteger(v) || v < 0 || v > 13)) {
    throw new Error('invalid-dds-canonical-table');
  }
  const strains = ['N', 'S', 'H', 'D', 'C'];
  const seats = ['N', 'S', 'E', 'W'];
  const table = {};
  let k = 0;
  for (const strain of strains) {
    table[strain] = {};
    for (const seat of seats) table[strain][seat] = vals[k++];
  }
  return table;
}

class NativeDdsEngine {
  constructor() {
    this.proc = null;
    this.reader = null;
    this.startPromise = null;
    this.queue = Promise.resolve();
    this.requests = 0;
    this.tables = 0;
    this.restarts = 0;
    this.lastMs = null;
    this.startedAt = null;
  }
  _isAlive() { return !!(this.proc && this.proc.exitCode === null && !this.proc.killed); }
  _kill() {
    if (this.proc) { try { this.proc.kill('SIGKILL'); } catch (_) {} }
    this.proc = null;
    this.reader = null;
    this.startPromise = null;
  }
  async ensureStarted() {
    if (this._isAlive() && this.reader) return;
    if (this.startPromise) return this.startPromise;
    this.startPromise = (async () => {
      const bin = await ensureBinary();
      const proc = spawn(bin, [String(THREADS), String(BATCH_SIZE)], {
        stdio: ['pipe', 'pipe', 'pipe'], env: { ...process.env }
      });
      this.proc = proc;
      this.reader = new LineReader(proc.stdout);
      let stderr = '';
      proc.stderr.setEncoding('utf8');
      proc.stderr.on('data', c => { stderr = (stderr + c).slice(-2000); });
      proc.on('exit', () => {
        if (this.proc === proc) {
          this.proc = null;
          this.reader = null;
          this.startPromise = null;
        }
      });
      proc.stdin.write('PING\n');
      const pong = await this.reader.readLine(START_TIMEOUT_MS);
      if (pong !== 'PONG') throw new Error(`dds-startup-handshake:${pong}:${stderr}`);
      this.startedAt = Date.now();
    })();
    try { await this.startPromise; }
    catch (err) { this._kill(); throw err; }
    finally { if (this._isAlive()) this.startPromise = null; }
  }
  solve(pbns) {
    const task = () => this._solveWithRetry(pbns);
    const run = this.queue.then(task, task);
    this.queue = run.catch(() => {});
    return run;
  }
  async _solveWithRetry(pbns) {
    let lastErr;
    for (let attempt = 0; attempt < 2; attempt++) {
      try { return await this._solveOnce(pbns); }
      catch (err) { lastErr = err; this.restarts += 1; this._kill(); }
    }
    throw lastErr || new Error('dds-failure');
  }
  async _solveOnce(pbns) {
    await this.ensureStarted();
    const started = Date.now();
    this.proc.stdin.write(`${pbns.length}\n${pbns.join('\n')}\n`);
    const head = await this.reader.readLine(RESPONSE_TIMEOUT_MS);
    if (head.startsWith('ERR\t')) throw new Error(head.slice(4));
    if (head !== `OK\t${pbns.length}`) throw new Error(`dds-bad-header:${head}`);
    const rows = [];
    for (let i = 0; i < pbns.length; i++) rows.push(await this.reader.readLine(RESPONSE_TIMEOUT_MS));
    const tables = rows.map(decodeCanonical);
    this.requests += 1;
    this.tables += pbns.length;
    this.lastMs = Date.now() - started;
    return tables;
  }
}

const GLOBAL_KEY = '__PLAY_R86_NATIVE_DDS_ENGINE__';
const engine = globalThis[GLOBAL_KEY] || (globalThis[GLOBAL_KEY] = new NativeDdsEngine());

function isAllowedOrigin(origin) {
  if (!origin) return true;
  if (ALLOWED_ORIGINS.has(origin)) return true;
  if (process.env.VERCEL_ENV !== 'production' && /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) return true;
  return false;
}
function applyCors(req, res) {
  const origin = req && req.headers && req.headers.origin;
  if (origin && isAllowedOrigin(origin)) res.setHeader('Access-Control-Allow-Origin', origin);
  res.setHeader('Vary', 'Origin');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Access-Control-Max-Age', '600');
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');
  res.setHeader('X-Play-DDS-Release', RELEASE);
  return isAllowedOrigin(origin);
}
function rateSubject(req) {
  const forwarded = String(req.headers['x-forwarded-for'] || '');
  const realIp = String(req.headers['x-real-ip'] || '');
  const ip = String((forwarded && forwarded.split(',')[0]) || realIp || 'unknown').trim().slice(0, 128);
  return crypto.createHash('sha256').update(ip, 'utf8').digest('hex').slice(0, 32);
}
function applyRateLimit(req, cost) {
  const now = Date.now();
  if (now - rateState.windowStart >= RATE_WINDOW_MS) {
    rateState.windowStart = now;
    rateState.globalCount = 0;
    rateState.clients.clear();
  }
  const subject = rateSubject(req);
  const clientCount = (rateState.clients.get(subject) || 0) + cost;
  if (clientCount > RATE_DEALS_PER_CLIENT) return -1;
  if (rateState.globalCount + cost > RATE_DEALS_GLOBAL) return -2;
  rateState.clients.set(subject, clientCount);
  rateState.globalCount += cost;
  return 1;
}
function validatePbnDeal(pbn) {
  if (typeof pbn !== 'string' || pbn.length === 0 || pbn.length > MAX_PBN_LENGTH) return false;
  const m = pbn.trim().match(/^([NESW]):(.+)$/);
  if (!m) return false;
  const hands = m[2].trim().split(/\s+/);
  if (hands.length !== 4) return false;
  const seen = new Set();
  for (const handText of hands) {
    const suits = handText.split('.');
    if (suits.length !== 4) return false;
    let cardCount = 0;
    for (let i = 0; i < 4; i++) {
      let ranks = suits[i].toUpperCase();
      if (ranks === '-') ranks = '';
      if (!/^[AKQJT98765432]*$/.test(ranks)) return false;
      cardCount += ranks.length;
      const suit = 'SHDC'[i];
      for (const rank of ranks) {
        const card = suit + rank;
        if (seen.has(card)) return false;
        seen.add(card);
      }
    }
    if (cardCount !== 13) return false;
  }
  return seen.size === 52;
}

module.exports = async function handler(req, res) {
  if (!applyCors(req, res)) return res.status(403).json({ error: 'origin-forbidden' });
  if (req.method === 'OPTIONS') return res.status(204).end();

  if (req.method === 'GET') {
    try {
      await engine.ensureStarted();
      const wantsSelftest = /(?:\?|&)selftest=1(?:&|$)/.test(String(req.url || ''));
      let selftest = null;
      if (wantsSelftest) {
        const started = Date.now();
        const tables = await engine.solve([SELFTEST_PBN]);
        const canonical = ['N','S','H','D','C']
          .flatMap(strain => ['N','S','E','W'].map(seat => tables[0][strain][seat])).join(',');
        selftest = { ok: canonical === SELFTEST_CANONICAL, elapsedMs: Date.now() - started, canonical, expected: SELFTEST_CANONICAL };
        if (!selftest.ok) return res.status(500).json({ ok: false, release: RELEASE, selftest });
      }
      return res.status(200).json({
        ok: true, release: RELEASE, engine: ENGINE, threads: THREADS, batchSize: BATCH_SIZE,
        maxItems: MAX_ITEMS, binarySha256: BIN_SHA256, requests: engine.requests,
        tables: engine.tables, restarts: engine.restarts, lastMs: engine.lastMs,
        startedAt: engine.startedAt, selftest
      });
    } catch (err) {
      return res.status(503).json({ ok: false, error: err && err.message ? err.message : String(err) });
    }
  }

  if (req.method !== 'POST') {
    res.setHeader('Allow', 'GET, POST, OPTIONS');
    return res.status(405).json({ error: 'method-not-allowed' });
  }

  const { items } = req.body || {};
  if (!Array.isArray(items) || items.length === 0 || items.length > MAX_ITEMS) {
    return res.status(400).json({ error: `items[] requis (1..${MAX_ITEMS})` });
  }
  const ids = [];
  const pbns = [];
  for (const item of items) {
    if (!item || !validatePbnDeal(item.pbn)) return res.status(400).json({ error: 'Donne PBN DDS invalide.' });
    ids.push(item.id);
    pbns.push(item.pbn.trim());
  }

  const rate = applyRateLimit(req, items.length);
  if (rate < 0) {
    res.setHeader('Retry-After', '60');
    return res.status(429).json({ error: 'dds-rate-limited', scope: rate === -1 ? 'client' : 'global' });
  }

  try {
    const started = Date.now();
    const tables = await engine.solve(pbns);
    res.setHeader('X-DDS-Elapsed-Ms', String(Date.now() - started));
    res.setHeader('X-DDS-Tables', String(tables.length));
    return res.status(200).json({ results: tables.map((table, i) => ({ id: ids[i], table })) });
  } catch (err) {
    return res.status(503).json({ error: 'dds-native-failure', detail: err && err.message ? err.message : String(err) });
  }
};
