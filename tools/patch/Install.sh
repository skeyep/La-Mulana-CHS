#!/bin/bash
set -u
base="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'ERROR: Python 3 is required. SteamOS includes python3.' >&2
    status=1
else
    python3 "$base/Patch.py" --action Install "$@"
    status=$?
fi
if [[ -t 0 && -z "${LM_CHS_NO_PAUSE:-}" ]]; then
    read -r -p 'Press Enter to close...' _
fi
exit "$status"
