import httpx, json, sys

url='http://127.0.0.1:8889/api/analyze'
sample = sys.argv[1] if len(sys.argv)>1 else 'brooklyn-drone-chase'
with httpx.Client(timeout=None) as client:
    with client.stream('POST', url, json={'sample_id':sample}) as r:
        if r.status_code!=200:
            # read body for debug
            txt = r.read()
            print('ERROR STATUS', r.status_code, txt)
            sys.exit(1)
        buf=''
        for chunk in r.iter_bytes():
            if not chunk:
                continue
            s = chunk.decode('utf-8', errors='ignore')
            buf += s
            while '\n\n' in buf:
                part, buf = buf.split('\n\n',1)
                if not part.strip():
                    continue
                lines = [l for l in part.splitlines() if l.strip()]
                ev = {'event':None,'data':''}
                for ln in lines:
                    if ln.startswith('event:'):
                        ev['event']=ln.split(':',1)[1].strip()
                    elif ln.startswith('data:'):
                        ev['data'] += ln.split(':',1)[1].strip()
                print('EVENT', ev['event'])
                try:
                    parsed = json.loads(ev['data'])
                except Exception:
                    parsed = None
                if ev['event']=='brief':
                    print('BRIEF RECEIVED')
                    print('BRIEF KEYS:', list(parsed.keys()) if isinstance(parsed,dict) else type(parsed))
                    sys.exit(0)
        print('STREAM CLOSED')
