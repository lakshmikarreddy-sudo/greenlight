import httpx
import json
import sys

BASE = 'http://127.0.0.1:8889'

def get(path):
    r = httpx.get(BASE + path, timeout=10.0)
    print(f"GET {path} -> {r.status_code}")
    print(r.text[:1000])


def stream_analyze(payload):
    print('\nPOST /api/analyze (stream) payload:', payload)
    with httpx.stream('POST', BASE + '/api/analyze', json=payload, timeout=None) as r:
        print('status', r.status_code)
        if r.status_code != 200:
            print('Non-200 response:', r.text)
            return
        buf = ''
        brief = None
        parsed_count = 0
        for chunk in r.iter_bytes():
            if not chunk:
                continue
            buf += chunk.decode('utf-8', errors='ignore')
            parts = buf.split('\n\n')
            buf = parts.pop()
            for p in parts:
                if not p.strip():
                    continue
                lines = [ln for ln in p.splitlines() if ln.strip()]
                ev = {'event': None, 'data': ''}
                for ln in lines:
                    if ln.startswith('event:'):
                        ev['event'] = ln.split('event:',1)[1].strip()
                    elif ln.startswith('data:'):
                        ev['data'] += ln.split('data:',1)[1].strip()
                print('SSE EVENT:', ev['event'])
                if ev['data']:
                    try:
                        parsed = json.loads(ev['data'])
                    except Exception:
                        parsed = None
                else:
                    parsed = None
                if ev['event'] == 'screenplay_parsed':
                    parsed_count += 1
                if ev['event'] == 'brief':
                    print('Received brief payload (truncated):')
                    print(json.dumps(parsed.get('data',{}), indent=2)[:2000])
                    brief = parsed.get('data', {}) if isinstance(parsed, dict) else None
                    # stop after brief for smoke test
                    return parsed_count, brief
        return parsed_count, brief


def sample_cycle(sid):
    payload = {'sample_id': sid}
    print(f'\n=== SAMPLE: {sid} ===')
    parsed_count, brief = stream_analyze(payload)
    print(f'Parsed count for {sid}: {parsed_count}')
    print(f'Brief keys for {sid}: {list(brief.keys()) if brief else None}')
    return parsed_count, brief


if __name__ == '__main__':
    try:
        get('/')
        get('/api/health')
        samples = httpx.get(BASE + '/api/samples', timeout=10.0).json()
        print('SAMPLE_IDS', [s['id'] for s in samples])

        for scenario in [s['id'] for s in samples]:
            sample_cycle(scenario)
    except Exception as e:
        print('ERROR', e)
        sys.exit(2)
