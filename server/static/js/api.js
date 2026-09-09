// API helpers: fetch samples and stream analysis via POST SSE-like streaming
export async function fetchSamples(){
  const res = await fetch('/api/samples');
  return res.json();
}

// parse SSE chunks from streaming fetch response
export async function streamAnalyze(payload, onEvent){
  const resp = await fetch('/api/analyze', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(payload),
  });
  if(!resp.ok) throw new Error('Analyze request failed')
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  while(true){
    const {done, value} = await reader.read();
    if(done) break;
    buf += dec.decode(value, {stream:true});
    let parts = buf.split('\n\n');
    buf = parts.pop();
    for(const p of parts){
      if(!p.trim()) continue;
      const lines = p.split(/\r?\n/);
      let ev = {event:null, data:''};
      for(const ln of lines){
        if(ln.startsWith('event:')) ev.event = ln.slice(6).trim();
        else if(ln.startsWith('data:')) ev.data += ln.slice(5).trim();
      }
      try{
        ev.parsed = JSON.parse(ev.data);
      }catch(e){ ev.parsed = null }
      onEvent(ev);
    }
  }
}
