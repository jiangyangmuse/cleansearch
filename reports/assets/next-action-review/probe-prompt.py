"""Replay three captured public fast materials against the revised prompt.
The model temperature and warm state are not controlled; this is a small audit,
not a causal accuracy benchmark or a repeat of HTTP/SSE protocol acceptance.
"""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'apps/api'))
from app.core.llm import OpenAICompatibleClient
from app.core.session_store import Snapshot, Source
from app.core.summarize import LLMSummarizer

async def main():
    before=json.loads((Path(__file__).parent/'summary-12.json').read_text(encoding='utf-8'))
    rows=[]
    summarizer=LLMSummarizer(OpenAICompatibleClient('http://127.0.0.1:11434/v1','ollama','qwen3.5-4b-local:latest',90,reasoning_effort='none'))
    for row in before['rows']:
        if row['mode']!='fast' or row['query'] not in ('Rust 所有权 借用','HTTP/2 多路复用','Python GIL 并发'):
            continue
        by_id={item['id']:item for item in row['search']['sources']}
        sources=[]
        for cite in row['citations']:
            item=by_id[cite['result_id']]
            sources.append(Source(result_id=item['id'],url=item['url'],title=item['title'],snippet=item['snippet'],domain=urlsplit(item['url']).hostname))
        material=json.dumps([s.__dict__ for s in sources],sort_keys=True,ensure_ascii=False).encode()
        snapshot=Snapshot('public-replay',row['query'],sources,'searxng')
        started=time.perf_counter()
        text=''
        first=None
        async for chunk in summarizer.stream(snapshot):
            if first is None:
                first=round((time.perf_counter()-started)*1000)
            text+=chunk
        mentions=sorted(set(int(n) for n in re.findall(r'\[(\d+)\]',text)))
        result={'query':row['query'],'source_sha256':hashlib.sha256(material).hexdigest(),
                'same_source_ids':[s.result_id for s in sources],'before_text':row['text'],'after_text':text,
                'first_ms':first,'total_ms':round((time.perf_counter()-started)*1000),
                'numbered_mentions':mentions,'numbered_mentions_valid':bool(mentions) and set(mentions).issubset(range(1,len(sources)+1)),
                'factuality':'requires-manual-review'}
        rows.append(result)
        (Path(__file__).parent/'prompt-replay.json').write_text(json.dumps({'scope':__doc__,'measured_at':datetime.now(timezone.utc).isoformat(),'rows':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'query':row['query'],'mentions_valid':result['numbered_mentions_valid'],'first_ms':first}),flush=True)

asyncio.run(main())
