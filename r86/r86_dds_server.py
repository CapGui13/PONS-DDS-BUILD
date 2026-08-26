#!/usr/bin/env python3
import atexit
import json
import os
import re
import select
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', '8080'))
RUNNER = os.environ.get('DDS_RUNNER', '/app/r86_dds_daemon')
THREADS = int(os.environ.get('DDS_THREADS', '2'))
BATCH = int(os.environ.get('DDS_BATCH_SIZE', '24'))
MAX_ITEMS = int(os.environ.get('DDS_MAX_ITEMS', '40'))
REQUEST_TIMEOUT = float(os.environ.get('DDS_REQUEST_TIMEOUT_SEC', '20'))
MAX_BODY = int(os.environ.get('DDS_MAX_BODY_BYTES', str(128 * 1024)))
ALLOWED_ORIGINS = {
    x.strip() for x in os.environ.get(
        'DDS_ALLOWED_ORIGINS',
        'https://capgui13.github.io,http://127.0.0.1,http://localhost'
    ).split(',') if x.strip()
}
PBN_RE = re.compile(r'^[NESW]:[^\r\n\t]{40,180}$')
STRAINS = ('N', 'S', 'H', 'D', 'C')
SEATS = ('N', 'S', 'E', 'W')

class Engine:
    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.requests = 0
        self.tables = 0
        self.restarts = 0
        self.last_ms = None
        self.max_child_rss_kb = 0
        self.start()

    def start(self):
        self.stop()
        self.proc = subprocess.Popen(
            [RUNNER, str(THREADS), str(BATCH)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._write('PING\n')
        pong = self._readline(5.0)
        if pong != 'PONG':
            self.stop()
            raise RuntimeError(f'DDS daemon failed startup handshake: {pong!r}')

    def stop(self):
        p = self.proc
        self.proc = None
        if not p:
            return
        try:
            if p.poll() is None and p.stdin:
                p.stdin.write('QUIT\n'); p.stdin.flush()
        except Exception:
            pass
        try:
            p.wait(timeout=2)
        except Exception:
            try: p.kill()
            except Exception: pass

    def _write(self, data):
        if not self.proc or self.proc.poll() is not None or not self.proc.stdin:
            raise RuntimeError('DDS daemon unavailable')
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def _readline(self, timeout):
        if not self.proc or not self.proc.stdout:
            raise RuntimeError('DDS daemon unavailable')
        ready, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if not ready:
            raise TimeoutError('DDS daemon response timeout')
        line = self.proc.stdout.readline()
        if line == '':
            err = ''
            try:
                if self.proc.stderr: err = self.proc.stderr.read()[-1000:]
            except Exception:
                pass
            raise RuntimeError(f'DDS daemon closed pipe: {err}')
        return line.rstrip('\r\n')

    @staticmethod
    def decode_canonical(line):
        vals = [int(x) for x in line.split(',')]
        if len(vals) != 20 or any(x < 0 or x > 13 for x in vals):
            raise RuntimeError('invalid DDS canonical table')
        table = {s: {} for s in STRAINS}
        k = 0
        for strain in STRAINS:
            for seat in SEATS:
                table[strain][seat] = vals[k]
                k += 1
        return table

    def solve(self, pbns):
        if not 1 <= len(pbns) <= MAX_ITEMS:
            raise ValueError('item count out of range')
        started = time.perf_counter()
        with self.lock:
            for attempt in range(2):
                try:
                    if not self.proc or self.proc.poll() is not None:
                        self.restarts += 1
                        self.start()
                    payload = str(len(pbns)) + '\n' + ''.join(p + '\n' for p in pbns)
                    self._write(payload)
                    head = self._readline(REQUEST_TIMEOUT)
                    if head.startswith('ERR\t'):
                        raise RuntimeError(head[4:])
                    if head != f'OK\t{len(pbns)}':
                        raise RuntimeError(f'unexpected DDS header {head!r}')
                    tables = [self.decode_canonical(self._readline(REQUEST_TIMEOUT)) for _ in pbns]
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    self.requests += 1
                    self.tables += len(pbns)
                    self.last_ms = elapsed_ms
                    try:
                        rss = 0
                        if self.proc:
                            with open(f'/proc/{self.proc.pid}/status', encoding='utf-8') as fh:
                                for line in fh:
                                    if line.startswith('VmRSS:'):
                                        rss = int(line.split()[1]); break
                        self.max_child_rss_kb = max(self.max_child_rss_kb, rss)
                    except Exception:
                        pass
                    return tables, elapsed_ms
                except (BrokenPipeError, RuntimeError, TimeoutError):
                    self.restarts += 1
                    self.stop()
                    if attempt == 0:
                        self.start()
                        continue
                    raise

ENGINE = Engine()
atexit.register(ENGINE.stop)

class Handler(BaseHTTPRequestHandler):
    server_version = 'PLAY-DDS-R86/1.0'

    def log_message(self, fmt, *args):
        print(f'{self.client_address[0]} - {fmt % args}', flush=True)

    def _cors(self):
        origin = self.headers.get('Origin')
        if origin in ALLOWED_ORIGINS:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')

    def _json(self, status, obj, extra_headers=None):
        raw = json.dumps(obj, separators=(',', ':')).encode('utf-8')
        self.send_response(status)
        self._cors()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Play-DDS-Release', 'R86')
        if extra_headers:
            for k, v in extra_headers.items(): self.send_header(k, str(v))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Max-Age', '86400')
        self.end_headers()

    def do_GET(self):
        if self.path not in ('/healthz', '/api/dds/healthz'):
            return self._json(404, {'error': 'not-found'})
        p = ENGINE.proc
        ok = bool(p and p.poll() is None)
        self._json(200 if ok else 503, {
            'ok': ok,
            'release': 'R86',
            'engine': 'DDS-2.9.1-native',
            'threads': THREADS,
            'batchSize': BATCH,
            'maxItems': MAX_ITEMS,
            'requests': ENGINE.requests,
            'tables': ENGINE.tables,
            'restarts': ENGINE.restarts,
            'lastMs': ENGINE.last_ms,
            'maxChildRssKb': ENGINE.max_child_rss_kb,
        })

    def do_POST(self):
        if self.path != '/api/dds':
            return self._json(404, {'error': 'not-found'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self._json(400, {'error': 'bad-content-length'})
        if length < 2 or length > MAX_BODY:
            return self._json(413, {'error': 'body-size'})
        try:
            payload = json.loads(self.rfile.read(length))
        except Exception:
            return self._json(400, {'error': 'invalid-json'})
        items = payload.get('items') if isinstance(payload, dict) else None
        if not isinstance(items, list) or not (1 <= len(items) <= MAX_ITEMS):
            return self._json(400, {'error': 'items-must-be-array-1-to-40'})
        pbns = []
        ids = []
        for i, item in enumerate(items):
            if not isinstance(item, dict) or 'id' not in item or not isinstance(item.get('pbn'), str):
                return self._json(400, {'error': f'bad-item-{i}'})
            pbn = item['pbn'].strip()
            if not PBN_RE.match(pbn) or pbn.count(' ') != 3:
                return self._json(400, {'error': f'bad-pbn-{i}'})
            ids.append(item['id'])
            pbns.append(pbn)
        try:
            tables, elapsed_ms = ENGINE.solve(pbns)
        except TimeoutError:
            return self._json(504, {'error': 'dds-timeout'})
        except Exception as exc:
            return self._json(500, {'error': 'dds-failure', 'detail': str(exc)[:200]})
        results = [{'id': ids[i], 'table': tables[i]} for i in range(len(ids))]
        self._json(200, {'results': results}, {
            'X-DDS-Elapsed-Ms': f'{elapsed_ms:.1f}',
            'X-DDS-Tables': len(results),
        })

if __name__ == '__main__':
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print(json.dumps({'event':'listen','host':HOST,'port':PORT,'threads':THREADS,'batch':BATCH,'maxItems':MAX_ITEMS}), flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        ENGINE.stop()
