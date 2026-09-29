"""Explicit manual work timer; does not monitor user activity."""
from contextlib import contextmanager
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import tempfile
from .common import parse_time, utc_now, read_json


def state_path(directory, session_id):
    return Path(directory) / (hashlib.sha256(session_id.encode('utf-8')).hexdigest() + '.json')


def load_state(directory, session_id):
    path = state_path(directory, session_id)
    if not path.exists():
        return None
    data = read_json(path)
    if (not isinstance(data, dict) or data.get('version') != 1 or data.get('session_id') != session_id
        or data.get('status') not in {'active','paused','stopped'} or not isinstance(data.get('intervals'),list)):
        raise ValueError('Invalid manual timer state; preserve it and inspect the selected state directory')
    for interval in data['intervals']:
        if not isinstance(interval,dict) or set(interval) != {'start','end'}:
            raise ValueError('Invalid manual timer interval')
        a,b=parse_time(interval['start']),parse_time(interval['end'])
        if not a or not b or b<a:
            raise ValueError('Invalid manual timer boundaries')
    if (data['status']=='active') != (data.get('open_start') is not None):
        raise ValueError('Invalid manual timer open state')
    if data.get('open_start') is not None and parse_time(data['open_start']) is None:
        raise ValueError('Invalid manual timer timestamp')
    return data


@contextmanager
def lock_state(path):
    lock=path.with_suffix('.lock')
    try:
        fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError as exc:
        raise ValueError('Manual timer is locked by another operation; retry when it finishes') from exc
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def track(action, directory, session_id, now=None):
    now=now or utc_now()
    current=parse_time(now)
    if not current:
        raise ValueError('Manual timer requires a real timezone-aware clock')
    if action not in {'start','pause','resume','stop','status'}:
        raise ValueError('Unknown manual timer action')
    if not isinstance(session_id,str) or not session_id.strip():
        raise ValueError('Manual timer requires a nonempty session ID')
    directory=Path(directory)
    if action=='status':
        state=load_state(directory,session_id)
        return {'status':state['status'] if state else 'not_started','human':summary(directory,session_id,now)}
    directory.mkdir(parents=True,exist_ok=True)
    path=state_path(directory,session_id)
    with lock_state(path):
        state=load_state(directory,session_id)
        if state is None:
            if action in {'pause','stop'}:
                return {'status':'not_started','human':None}
            state={'version':1,'session_id':session_id,'status':'stopped','open_start':None,'intervals':[]}
        if action in {'start','resume'} and state['status']!='active':
            if state['intervals'] and current<parse_time(state['intervals'][-1]['end']):
                raise ValueError('Clock precedes the previous timer interval')
            state['status']='active'
            state['open_start']=now
        elif action in {'pause','stop'}:
            if state['status']=='active':
                if current<parse_time(state['open_start']):
                    raise ValueError('Clock moved backwards; timer was not changed')
                state['intervals'].append({'start':state['open_start'],'end':now})
                state['open_start']=None
            state['status']='paused' if action=='pause' else 'stopped'
        state['updated_at']=now
        state['basis']='declared'
        fd,tmp=tempfile.mkstemp(prefix='.timer-',dir=directory)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as handle:
                json.dump(state,handle,indent=2,ensure_ascii=False)
                handle.write('\n')
            os.replace(tmp,path)
        finally:
            Path(tmp).unlink(missing_ok=True)
    return {'status':state['status'],'state':str(path),'human':summary(directory,session_id,now)}


def summary(directory, session_id, cutoff):
    state=load_state(directory,session_id)
    if state is None:
        return None
    end=parse_time(cutoff)
    if not end:
        raise ValueError('Timer cutoff must include a timezone')
    intervals=[]
    for item in state['intervals']:
        a,b=parse_time(item['start']),min(parse_time(item['end']),end)
        if a<=b:
            intervals.append((a,b))
    is_open=state['status']=='active' and parse_time(state['open_start'])<=end
    if is_open:
        intervals.append((parse_time(state['open_start']),end))
    if not intervals:
        return None
    merged=[]
    for a,b in sorted(intervals):
        if merged and a<=merged[-1][1]:
            merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:
            merged.append((a,b))
    seconds=sum((Decimal(str((b-a).total_seconds())) for a,b in merged),Decimal(0))
    return {'seconds':str(seconds),'basis':'declared','coverage':'partial','open':is_open}
