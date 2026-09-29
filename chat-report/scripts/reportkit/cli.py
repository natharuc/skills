"""One command interface for discovery, collection, tracking, and visual reports."""
import argparse
import importlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from .common import diagnostic, parse_time, read_json, utc_now, validate_collection
from . import tracking

ADAPTERS={'cursor':'cursor','codex':'codex','claude':'claude','github-copilot':'copilot','antigravity':'antigravity'}
ALIASES={'copilot':'github-copilot','claude-code':'claude'}


def adapter(name):
    return importlib.import_module('reportkit.adapters.'+ADAPTERS[name])


def harness_name(value):
    value=ALIASES.get(value,value)
    if value not in {*ADAPTERS,'auto'}:
        raise argparse.ArgumentTypeError('Choose auto, cursor, codex, claude, github-copilot, or antigravity')
    return value


def known_roots(name):
    return adapter(name).roots(Path.home(),dict(os.environ),platform.system())


def list_sessions(harness, source=None, limit=100):
    names=list(ADAPTERS) if harness=='auto' else [harness]
    result=[]
    warnings=[]
    seen=set()
    saturated=False
    for name in names:
        sources=[Path(source).expanduser()] if source else known_roots(name)
        for location in sources:
            if not location.exists():
                continue
            try:
                entries=adapter(name).sessions(location,limit=limit)
            except (ValueError,OSError,UnicodeError) as exc:
                warnings.append({'harness':name,'code':'source_unreadable','message':str(exc)})
                continue
            if len(entries)>=limit:
                saturated=True
            for item in entries:
                if not isinstance(item,dict) or not isinstance(item.get('session_id'),str) or not item.get('source'):
                    continue
                key=(name,item['session_id'],str(Path(item['source']).resolve()))
                if key in seen:
                    continue
                seen.add(key)
                entry={'harness':name,'session_id':item['session_id'],'source':key[2]}
                if parse_time(item.get('started_at')):
                    entry['started_at']=item['started_at']
                result.append(entry)
    result.sort(key=lambda x:(x['harness'],x['session_id'],x['source']))
    return {'sessions':result[:limit],'scan_limit':limit,'truncated':saturated or len(result)>limit,'diagnostics':warnings}


def resolve_scope(args):
    harness=args.harness
    session=args.session
    if not session and harness in {'auto','codex'} and not args.source:
        session=os.environ.get('CODEX_THREAD_ID') or None
        if session:
            harness='codex'
    if args.source and harness!='auto' and session:
        source=Path(args.source).expanduser().resolve()
        if not source.exists():
            raise ValueError('Selected source does not exist on this computer')
        if source.is_file():
            return harness,session,source
    if not session and not args.source:
        raise ValueError('Supply --session from current harness metadata, or --source for an explicit export; use sessions to list candidates')
    found=list_sessions(harness,args.source,limit=1000)
    if found['truncated']:
        raise ValueError('Session discovery reached its limit; supply the exact --source file before resolving scope')
    candidates=[item for item in found['sessions'] if not session or item['session_id']==session]
    if len(candidates)!=1:
        if not candidates:
            raise ValueError('No matching readable session found; use doctor/sessions and specify --harness, --session, and --source. A remote environment may not have the desktop files.')
        raise ValueError('Several sources match; specify --harness and the exact --source. No newest-session guess was made.')
    item=candidates[0]
    return item['harness'],item['session_id'],Path(item['source'])


def collect(args, cutoff):
    harness,session,source=resolve_scope(args)
    result=adapter(harness).collect(source,session,cutoff=cutoff,strict_cutoff=bool(args.cutoff))
    result['cutoff']=cutoff
    validate_collection(result)
    if result['harness']!=harness or result['session_id']!=session:
        raise ValueError('Collector identity does not match the requested scope')
    return result


def serialize(data):
    return json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n'


def save_files(files, overwrite=False):
    paths=[Path(path).expanduser().resolve() for path in files]
    if len(set(paths))!=len(paths):
        raise ValueError('Output paths must be distinct')
    if not overwrite and any(path.exists() for path in paths):
        raise ValueError('An output file already exists; choose another path or use --overwrite')
    for path,content in zip(paths,files.values()):
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('w' if overwrite else 'x',encoding='utf-8',newline='\n') as handle:
            handle.write(content)
    return [str(path) for path in paths]


def open_html(path):
    path=Path(path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in {'.html','.htm'}:
        raise ValueError('open requires an existing HTML report')
    if os.environ.get('SSH_CONNECTION') or os.environ.get('SSH_TTY'):
        return {'status':'unavailable','reason':'SSH session: use the host preview or open the file on the desktop computer'}
    system=platform.system()
    if system=='Windows':
        try:
            os.startfile(str(path))
        except OSError:
            return {'status':'unavailable','reason':'No registered local HTML application could be launched'}
    elif system=='Darwin':
        command=shutil.which('open')
        if not command:
            return {'status':'unavailable','reason':'macOS open command is unavailable'}
        try:
            subprocess.run([command,str(path)],check=True,timeout=10,capture_output=True)
        except (OSError,subprocess.SubprocessError):
            return {'status':'unavailable','reason':'The macOS desktop could not open the file'}
    else:
        command=shutil.which('xdg-open')
        if not command or not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
            return {'status':'unavailable','reason':'No Linux desktop preview detected; use the host HTML preview'}
        try:
            subprocess.run([command,str(path)],check=True,timeout=10,capture_output=True)
        except (OSError,subprocess.SubprocessError):
            return {'status':'unavailable','reason':'The Linux desktop could not open the file'}
    return {'status':'launch_requested','reason':'The operating system accepted the open request; visual rendering still needs host verification'}


def default_output(data):
    safe=re.sub(r'[^A-Za-z0-9_.-]+','-',data['session_id'])[:80].strip('.-') or 'session'
    stamp=re.sub(r'[^0-9]','',data['cutoff'])
    return Path.cwd()/'.chat-report'/'reports'/f'{data["harness"]}-{safe}-{stamp}.html'


def generate(data,args):
    from .presentation import build_presentation
    import render_report
    data=validate_collection(data)
    if not data.get('cutoff'):
        raise ValueError('Evidence needs an explicit cutoff; collect it with the command runner first')
    rates=read_json(args.rates) if args.rates else None
    human=tracking.summary(args.state_dir,data['session_id'],data['cutoff'])
    view=build_presentation(data,language=args.language,task=args.task,rates=rates,human=human,
                            hourly_rate=args.hourly_rate,labor_currency=args.currency)
    checked=render_report.validate(view)
    output=Path(args.output).expanduser() if args.output else default_output(data)
    if output.suffix.lower() not in {'.html','.htm'}:
        raise ValueError('Report output must end with .html or .htm')
    evidence=output.with_suffix('.evidence.json')
    presentation=output.with_suffix('.presentation.json')
    files={output:render_report.render(checked),evidence:serialize(data),presentation:serialize(view)}
    if args.fragment:
        files[output.with_name(output.stem+'.fragment.html')]=render_report.render(checked,fragment=True)
    source_inputs=[Path(p).expanduser().resolve() for p in [getattr(args,'input',None),args.rates,data.get('source')] if p]
    if any(Path(p).expanduser().resolve() in source_inputs for p in files):
        raise ValueError('An output path would overwrite a source or input file')
    written=save_files(files,overwrite=args.overwrite)
    opened=open_html(output) if args.open else {'status':'not_requested','reason':'Use the native host preview, or the open command on the desktop'}
    return {'status':'ok','harness':data['harness'],'session_id':data['session_id'],
            'files':written,'token_coverage':data['token_coverage'],'display':opened,
            'diagnostics':data['diagnostics']}


def parser():
    root=argparse.ArgumentParser(description=__doc__)
    root.add_argument('--version',action='version',version='chat-report 2.0')
    sub=root.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor',help='Inspect OS/runtime and known local data roots')
    listing=sub.add_parser('sessions',help='List bounded local session metadata')
    listing.add_argument('--harness',type=harness_name,default='auto')
    listing.add_argument('--source')
    listing.add_argument('--limit',type=int,default=100)
    def scope(p):
        p.add_argument('--harness',type=harness_name,default='auto')
        p.add_argument('--session')
        p.add_argument('--source')
        p.add_argument('--cutoff',help='ISO timestamp with timezone; defaults to invocation start')
    def report_options(p):
        p.add_argument('--output')
        p.add_argument('--language',choices=['en','pt-BR'],default='en')
        p.add_argument('--task')
        p.add_argument('--rates',help='Explicit model rates per million tokens')
        p.add_argument('--hourly-rate',help='Human hourly rate as a decimal string')
        p.add_argument('--currency',help='Three-letter currency for human labor')
        p.add_argument('--state-dir',default=str(Path.cwd()/'.chat-report'/'timers'))
        p.add_argument('--fragment',action='store_true')
        p.add_argument('--overwrite',action='store_true')
        p.add_argument('--open',action='store_true')
    collector=sub.add_parser('collect',help='Read one native session or supported export')
    scope(collector)
    collector.add_argument('--output')
    collector.add_argument('--overwrite',action='store_true')
    report=sub.add_parser('report',help='Collect, calculate, and compile the HTML in one command')
    scope(report)
    report_options(report)
    render=sub.add_parser('render',help='Compile a previously collected evidence JSON')
    render.add_argument('--input',required=True)
    report_options(render)
    timer=sub.add_parser('track',help='Track explicitly declared human work intervals')
    timer.add_argument('action',choices=['start','pause','resume','stop','status'])
    timer.add_argument('--session',required=True)
    timer.add_argument('--state-dir',default=str(Path.cwd()/'.chat-report'/'timers'))
    opener=sub.add_parser('open',help='Request a desktop preview of an existing HTML file')
    opener.add_argument('--path',required=True)
    return root


def main(argv=None):
    invocation=utc_now()
    args=parser().parse_args(argv)
    try:
        if args.command=='doctor':
            result={'status':'ok','system':platform.system(),'machine':platform.machine(),
                    'python':platform.python_version(),'executable':sys.executable,
                    'remote':bool(os.environ.get('SSH_CONNECTION') or os.environ.get('SSH_TTY')),
                    'wsl':bool(os.environ.get('WSL_DISTRO_NAME')),'adapters':{}}
            for name in ADAPTERS:
                result['adapters'][name]={'roots':[{'path':str(p),'exists':p.exists()} for p in known_roots(name)]}
            result['note']='Existing directories do not prove that usage metrics were recorded. Use sessions to identify a session.'
        elif args.command=='sessions':
            if not 1<=args.limit<=1000:
                raise ValueError('--limit must be between 1 and 1000')
            result=list_sessions(args.harness,args.source,args.limit)
        elif args.command in {'collect','report'}:
            cutoff=args.cutoff or invocation
            if not parse_time(cutoff):
                raise ValueError('--cutoff must be an ISO timestamp with timezone')
            if parse_time(cutoff)>parse_time(invocation):
                raise ValueError('--cutoff cannot be in the future')
            data=collect(args,cutoff)
            if args.command=='collect':
                if args.output:
                    if Path(args.output).expanduser().resolve()==Path(data['source']).expanduser().resolve():
                        raise ValueError('Output would overwrite the source')
                    result={'status':'ok','files':save_files({Path(args.output):serialize(data)},args.overwrite)}
                else:
                    result=data
            else:
                result=generate(data,args)
        elif args.command=='render':
            result=generate(read_json(args.input),args)
        elif args.command=='track':
            result=tracking.track(args.action,args.state_dir,args.session,invocation)
        else:
            result=open_html(args.path)
        print(serialize(result),end='')
        return 0
    except (ValueError,OSError,UnicodeError,ImportError) as exc:
        print(serialize({'status':'error','error':str(exc)}),file=sys.stderr,end='')
        return 2
