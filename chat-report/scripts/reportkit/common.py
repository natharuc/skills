"""Shared bounded readers and data contracts; never execute source content."""
from datetime import datetime, timezone
from pathlib import Path
import json
import math

TOKEN_KEYS = ('input_uncached', 'cache_read', 'cache_write_short', 'cache_write_long', 'output', 'total')
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_LINE_BYTES = 4 * 1024 * 1024
MAX_EVENTS = 250000


def parse_time(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def iso_time(value):
    parsed = parse_time(value)
    return parsed.isoformat().replace('+00:00', 'Z') if parsed else None


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def empty_result(harness, session_id, source):
    return {
        'schema_version': 1, 'harness': harness, 'session_id': session_id,
        'source': str(source), 'source_kind': 'native', 'started_at': None,
        'observed_until': None, 'tokens': dict.fromkeys(TOKEN_KEYS),
        'token_coverage': 'unavailable', 'model_usage': [], 'intervals': [],
        'time_basis': 'none', 'time_coverage': 'unavailable', 'billing': [],
        'event_count': 0, 'diagnostics': [],
    }


def diagnostic(result, code, message):
    item = {'code': code, 'message': message}
    if item not in result['diagnostics']:
        result['diagnostics'].append(item)
    return result


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Non-finite JSON constant')


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Non-finite JSON number')
    if isinstance(value, dict):
        for child in value.values():
            _finite(child)
    elif isinstance(value, list):
        for child in value:
            _finite(child)
    return value


def json_loads(content):
    try:
        return _finite(json.loads(content, object_pairs_hook=_pairs, parse_constant=_constant))
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('Malformed or excessively nested JSON') from exc


def read_json(path):
    path = Path(path)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('Source exceeds the 128 MiB reader limit')
    with path.open('rb') as handle:
        data = handle.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError('Source grew beyond the 128 MiB reader limit')
    return json_loads(data.decode('utf-8-sig'))


def read_jsonl(path):
    path = Path(path)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('Source exceeds the 128 MiB reader limit')
    size = 0
    events = 0
    with path.open('rb') as handle:
        line_number = 0
        while True:
            line = handle.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            line_number += 1
            size += len(line)
            if size > MAX_FILE_BYTES or len(line) > MAX_LINE_BYTES:
                raise ValueError('JSONL source exceeds a reader limit')
            if not line.strip():
                continue
            events += 1
            if events > MAX_EVENTS:
                raise ValueError('JSONL source exceeds the event limit')
            try:
                value = json_loads(line.decode('utf-8-sig' if line_number == 1 else 'utf-8'))
            except (ValueError, UnicodeError) as exc:
                raise ValueError(f'Malformed JSONL record at line {line_number}') from exc
            if not isinstance(value, dict):
                raise ValueError(f'Expected an object at line {line_number}')
            yield line_number, value


def validate_collection(data):
    """Validate collected/imported evidence without trusting labels as provenance."""
    allowed = {'schema_version','harness','session_id','source','source_kind','started_at',
               'observed_until','cutoff','tokens','token_coverage','model_usage','intervals',
               'time_basis','time_coverage','billing','event_count','diagnostics'}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError('Invalid collection object or unknown fields')
    if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise ValueError('collection.schema_version must be 1')
    if data.get('harness') not in {'cursor','codex','claude','github-copilot','antigravity'}:
        raise ValueError('Unknown harness in collection')
    for key in ('session_id','source','source_kind'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f'collection.{key} must be nonempty text')
    for key in ('started_at','observed_until','cutoff'):
        if data.get(key) is not None and parse_time(data[key]) is None:
            raise ValueError(f'collection.{key} must be a timestamp with timezone or null')
    cutoff = parse_time(data.get('cutoff'))
    for key in ('started_at','observed_until'):
        moment = parse_time(data.get(key))
        if moment and cutoff and moment > cutoff:
            raise ValueError(f'collection.{key} exceeds cutoff')
    if type(data.get('event_count')) is not int or data['event_count'] < 0:
        raise ValueError('collection.event_count must be a nonnegative integer')
    def tokens(value):
        if not isinstance(value, dict) or set(value) != set(TOKEN_KEYS):
            raise ValueError('Token data requires exactly the six documented keys')
        if any(v is not None and (type(v) is not int or v < 0) for v in value.values()):
            raise ValueError('Token values must be nonnegative integers or null')
    tokens(data.get('tokens'))
    coverage = {'complete','partial','unavailable'}
    for key in ('token_coverage','time_coverage'):
        if data.get(key, 'unavailable') not in coverage:
            raise ValueError('Invalid metric coverage')
    if data.get('time_basis') not in {'none','gross_turn','request'}:
        raise ValueError('Invalid time basis')
    for key in ('model_usage','intervals','billing','diagnostics'):
        if not isinstance(data.get(key), list):
            raise ValueError(f'collection.{key} must be a list')
    models = set()
    for item in data['model_usage']:
        if not isinstance(item,dict) or set(item) - {'model','tokens','coverage'}:
            raise ValueError('Invalid model usage entry')
        if not isinstance(item.get('model'),str) or not item['model'].strip() or item['model'] in models:
            raise ValueError('Model labels must be nonempty and unique')
        models.add(item['model'])
        tokens(item.get('tokens'))
        if item.get('coverage') not in coverage:
            raise ValueError('Invalid model coverage')
    for item in data['intervals']:
        if not isinstance(item,dict) or set(item) != {'start','end','agent_id'}:
            raise ValueError('Invalid execution interval fields')
        a,b = parse_time(item['start']),parse_time(item['end'])
        if not a or not b or b<a or (cutoff and b>cutoff):
            raise ValueError('Invalid execution interval boundaries')
        if not isinstance(item['agent_id'],str) or not item['agent_id']:
            raise ValueError('Interval requires agent identity')
    from decimal import Decimal, InvalidOperation
    import re
    for item in data['billing']:
        if not isinstance(item,dict) or set(item) != {'currency','amount','kind','coverage'}:
            raise ValueError('Invalid billing entry')
        if item['kind'] not in {'attributed','reference'} or item['coverage'] not in coverage:
            raise ValueError('Invalid billing qualification')
        if not isinstance(item['currency'],str) or not re.fullmatch(r'[A-Z]{3}',item['currency']):
            raise ValueError('Invalid billing currency')
        if not isinstance(item['amount'],str) or not re.fullmatch(r'\d+(?:\.\d+)?',item['amount']):
            raise ValueError('Billing amount must be a nonnegative decimal string')
        try:
            amount=Decimal(item['amount'])
        except InvalidOperation as exc:
            raise ValueError('Invalid billing amount') from exc
        if not amount.is_finite():
            raise ValueError('Non-finite billing amount')
    for item in data['diagnostics']:
        if not isinstance(item,dict) or set(item) != {'code','message'} or not all(isinstance(v,str) and v for v in item.values()):
            raise ValueError('Invalid diagnostic entry')
    return data
