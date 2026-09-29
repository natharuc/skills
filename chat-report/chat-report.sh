#!/bin/sh
# POSIX entry point. Use: sh /path/to/chat-report/chat-report.sh report ...
# Resolve resources beside this file, independent of the caller's directory.
launcher_path=$0
case "$launcher_path" in
    /*) ;;
    *) launcher_path=$PWD/$launcher_path ;;
esac
skill_dir=$(CDPATH= cd -P "$(dirname "$launcher_path")" && pwd) || exit 2
entry_point=$skill_dir/scripts/chat_report.py

if [ ! -f "$entry_point" ]; then
    printf '%s\n' 'chat-report: missing scripts/chat_report.py. Install the complete skill folder.' >&2
    exit 2
fi

runtime=
for candidate in python3 python; do
    candidate_path=$(command -v "$candidate" 2>/dev/null) || continue
    if "$candidate_path" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
        runtime=$candidate_path
        break
    fi
done

if [ -z "$runtime" ]; then
    printf '%s\n' 'chat-report: Python 3.10 or newer is required. Install it separately and make python3 or python available on PATH. No dependencies are downloaded by this launcher.' >&2
    exit 127
fi

# exec preserves the engine's exit status and streams without reconstructing or
# evaluating the argument list. Quoted "$@" preserves spaces and literal text.
exec "$runtime" "$entry_point" "$@"
