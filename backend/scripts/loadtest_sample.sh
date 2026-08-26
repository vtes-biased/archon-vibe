#!/usr/bin/env bash
# Samples DB connection state and per-unit memory to CSV while
# loadtest_stream.py runs; join on epoch against its phase bounds.
# Usage: loadtest_sample.sh <db_name> <out_csv> [interval_s] [unit ...]
set -euo pipefail

db="$1"
out="$2"
interval="${3:-1}"
shift $(( $# >= 3 ? 3 : 2 ))
units=("$@")
if [ ${#units[@]} -eq 0 ]; then
    units=(new-archon-backend nginx)
fi

header="epoch,active_backends,total_sessions"
for u in "${units[@]}"; do
    header+=",mem_${u}"
done
echo "$header" > "$out"
echo "sampling every ${interval}s into $out (ctrl-c to stop)"

while true; do
    line="$(date +%s)"
    line+=",$(sudo -u postgres psql -At -F, -c \
        "SELECT (SELECT count(*) FROM pg_stat_activity WHERE datname = '$db'),
                (SELECT sessions FROM pg_stat_database WHERE datname = '$db')")"
    for u in "${units[@]}"; do
        line+=",$(systemctl show -p MemoryCurrent --value "$u")"
    done
    echo "$line" >> "$out"
    sleep "$interval"
done
