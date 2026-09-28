"""Standalone KEEP-only context externalization benchmark. Python 3.12+."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
SYSTEM = 'Answer from the supplied records only. Later explicit revisions supersede earlier ones. Return only the exact requested value, no explanation or formatting. If not recorded, return UNKNOWN. Do not guess.'

def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def correct(actual, expected):
    return str(actual).strip().strip('`').strip().rstrip('.').casefold() == expected.casefold()

def cosine(a, b):
    if len(a) != len(b) or not a:
        raise ValueError('Embedding dimensions mismatch or empty vector')
    denominator = math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    if not denominator:
        raise ValueError('Zero embedding')
    return sum(x*y for x,y in zip(a,b))/denominator

def request(base, path, payload, key):
    headers = {'Content-Type':'application/json'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    req = urllib.request.Request(base.rstrip('/')+'/'+path, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)

def summarize(result):
    cases = result['cases']
    summary = {'n':len(cases)}
    for arm in ('full','handoff_only','recall'):
        summary[arm] = sum(correct(c[arm]['answer'],c['expected']) for c in cases)
    summary['evidence_at_5'] = sum(c['evidence_at_5'] for c in cases)
    tokens={}
    for arm in ('full','recall'):
        values=[c[arm].get('usage',{}).get('prompt_tokens') for c in cases]
        tokens[arm] = sum(values) if values and all(isinstance(v,int) for v in values) else None
    summary['prompt_tokens']=tokens
    summary['prompt_token_reduction_pct'] = 100*(1-tokens['recall']/tokens['full']) if tokens['full'] and tokens['recall'] is not None else None
    return summary

def dataset():
    return json.loads((ROOT/'data/corpus.json').read_text(encoding='utf-8'))

def prepare(data):
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE segments (ordinal INTEGER PRIMARY KEY, hash TEXT NOT NULL, exact TEXT NOT NULL)')
    for i,message in enumerate(data['messages']):
        db.execute('INSERT INTO segments VALUES (?,?,?)',(i,digest(message['content']),message['content']))
    hashes=[row[0] for row in db.execute('SELECT hash FROM segments ORDER BY ordinal')]
    manifest=digest(json.dumps(hashes,separators=(',',':')))
    handoff=('Context has been externalized. This is a navigation hint, not the complete record.\n'
             f'Manifest: {manifest}\nRetained segments: {len(hashes)}\n'
             'Use semantic recall to retrieve relevant exact records. Later revisions supersede earlier ones.\n'
             'First-record excerpt: '+data['messages'][0]['content'][:600])
    return db,handoff

def offline():
    data=dataset();db,handoff=prepare(data)
    rows=db.execute('SELECT ordinal, hash, exact FROM segments ORDER BY ordinal').fetchall()
    assert len(rows)==49
    assert all(h==digest(t) and t==data['messages'][i]['content'] for i,h,t in rows)
    assert all(0<=c['evidence_ordinal']<len(rows) for c in data['questions'])
    recorded=json.loads((ROOT/'results/original-run.json').read_text(encoding='utf-8'))
    summary=summarize(recorded)
    assert summary['full']==12 and summary['recall']==12 and summary['handoff_only']==1
    assert summary['evidence_at_5']==12
    assert summary['prompt_tokens']=={'full':96819,'recall':22296}
    print(json.dumps({'offline_integrity':'49/49','recorded_result_rescored':summary,'note':'No model was called. This validates fixtures and rescoring, not a fresh quality result.'},indent=2))

def run(args):
    required=['CHAT_BASE_URL','CHAT_MODEL','EMBED_BASE_URL','EMBED_MODEL']
    missing=[x for x in required if not os.environ.get(x)]
    if missing:
        raise SystemExit('Set environment variables: '+', '.join(missing))
    if args.output.exists():
        raise SystemExit('Output already exists; select a new --output path.')
    data=dataset();db,handoff=prepare(data)
    texts=[m['content'] for m in data['messages']]
    def embed(inputs):
        response=request(os.environ['EMBED_BASE_URL'],'embeddings',{'model':os.environ['EMBED_MODEL'],'input':inputs},os.environ.get('EMBED_API_KEY',''))
        items=sorted(response['data'],key=lambda x:x['index'])
        if [x['index'] for x in items]!=list(range(len(inputs))):
            raise ValueError('Incomplete embedding response')
        vectors=[x['embedding'] for x in items]
        if any(not v or any(not math.isfinite(x) for x in v) for v in vectors):
            raise ValueError('Invalid embedding')
        return vectors
    vectors=[]
    for offset in range(0,len(texts),8):
        vectors.extend(embed(texts[offset:offset+8]))
    full='\n\n'.join(f'[{i}] '+t for i,t in enumerate(texts))
    result={'scope':'portable-reference-v1; SQLite exact store, exhaustive cosine search, no reranker; deterministic handoff; KEEP only; fixed query, not autonomous agent','models':{'chat':os.environ['CHAT_MODEL'],'embedding':os.environ['EMBED_MODEL']},'corpus_sha256':digest((ROOT/'data/corpus.json').read_text(encoding='utf-8')),'handoff':handoff,'cases':[]}
    for case in data['questions']:
        vector=embed([case['question']])[0]
        ranked=sorted(range(len(texts)),key=lambda i:cosine(vector,vectors[i]),reverse=True)[:5]
        evidence=[]
        for i in ranked:
            h,t=db.execute('SELECT hash,exact FROM segments WHERE ordinal=?',(i,)).fetchone()
            assert digest(t)==h
            evidence.append(f'[{i}] '+t)
        recalled=handoff+'\n\nEXACT RECALLED RECORDS:\n'+'\n\n'.join(evidence)
        out={**case,'retrieved_ordinals':ranked,'evidence_at_5':case['evidence_ordinal'] in ranked}
        for arm,context in [('full',full),('handoff_only',handoff),('recall',recalled)]:
            started=time.perf_counter()
            response=request(os.environ['CHAT_BASE_URL'],'chat/completions',{'model':os.environ['CHAT_MODEL'],'temperature':0,'max_tokens':160,'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':'RECORDS:\n'+context+'\n\nQUESTION: '+case['question']}]},os.environ.get('CHAT_API_KEY',''))
            content=response['choices'][0]['message']['content']
            if not isinstance(content,str):
                raise ValueError('Missing textual answer')
            out[arm]={'answer':content,'correct':correct(content,case['expected']),'usage':response.get('usage',{}),'model':response.get('model'),'system_fingerprint':response.get('system_fingerprint'),'seconds':time.perf_counter()-started}
        result['cases'].append(out)
        result['summary']=summarize(result)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(case['id'], {a:out[a]['correct'] for a in ('full','handoff_only','recall')},flush=True)
    print(json.dumps(result['summary'],indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['offline','run','rescore'])
    parser.add_argument('--output',type=Path,default=Path('results/local-run.json'))
    parser.add_argument('--input',type=Path,default=ROOT/'results/original-run.json')
    args=parser.parse_args()
    if args.mode=='offline': offline()
    elif args.mode=='rescore': print(json.dumps(summarize(json.loads(args.input.read_text(encoding='utf-8'))),indent=2))
    else: run(args)
