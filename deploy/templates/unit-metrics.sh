#!/bin/sh
set -u
out=/var/lib/fluent-bit/textfile/units.prom
units="archon-backend.service archon-public-api.service archon-bot.service nginx.service fluent-bit.service postgres-backup.service"

psi() {
    awk -v kind="$2" -v metric="$1" '$1 == kind { split($5, t, "="); printf "%s %.6f\n", metric, t[2] / 1e6 }' "$3"
}

while :; do
    {
        echo "# TYPE node_pressure_cpu_waiting_seconds_total counter"
        psi node_pressure_cpu_waiting_seconds_total some /proc/pressure/cpu
        echo "# TYPE node_pressure_memory_waiting_seconds_total counter"
        psi node_pressure_memory_waiting_seconds_total some /proc/pressure/memory
        echo "# TYPE node_pressure_memory_stalled_seconds_total counter"
        psi node_pressure_memory_stalled_seconds_total full /proc/pressure/memory
        echo "# TYPE node_pressure_io_waiting_seconds_total counter"
        psi node_pressure_io_waiting_seconds_total some /proc/pressure/io
        echo "# TYPE node_pressure_io_stalled_seconds_total counter"
        psi node_pressure_io_stalled_seconds_total full /proc/pressure/io
        echo "# TYPE archon_unit_memory_bytes gauge"
        echo "# TYPE archon_unit_swap_bytes gauge"
        echo "# TYPE archon_unit_cpu_seconds_total counter"
        echo "# TYPE archon_unit_memory_stalled_seconds_total counter"
        echo "# TYPE archon_unit_io_read_bytes_total counter"
        echo "# TYPE archon_unit_io_written_bytes_total counter"
        echo "# TYPE archon_unit_io_reads_total counter"
        echo "# TYPE archon_unit_io_writes_total counter"
        echo "# TYPE archon_unit_io_stalled_seconds_total counter"
        for unit in $units $(systemctl list-units --plain --no-legend 'postgresql@*' | awk '{print $1}'); do
            dir=/sys/fs/cgroup$(systemctl show -P ControlGroup "$unit")
            [ "$dir" = /sys/fs/cgroup ] && continue
            label="{unit=\"$unit\"}"
            [ -r "$dir/memory.current" ] && echo "archon_unit_memory_bytes$label $(cat "$dir/memory.current")"
            [ -r "$dir/memory.swap.current" ] && echo "archon_unit_swap_bytes$label $(cat "$dir/memory.swap.current")"
            [ -r "$dir/cpu.stat" ] && awk -v l="$label" '$1 == "usage_usec" { printf "archon_unit_cpu_seconds_total%s %.6f\n", l, $2 / 1e6 }' "$dir/cpu.stat"
            [ -r "$dir/memory.pressure" ] && psi "archon_unit_memory_stalled_seconds_total$label" full "$dir/memory.pressure"
            [ -r "$dir/io.stat" ] && awk -v l="$label" '
                { for (i = 2; i <= NF; i++) { split($i, kv, "="); sum[kv[1]] += kv[2] } }
                END {
                    printf "archon_unit_io_read_bytes_total%s %.0f\n", l, sum["rbytes"]
                    printf "archon_unit_io_written_bytes_total%s %.0f\n", l, sum["wbytes"]
                    printf "archon_unit_io_reads_total%s %.0f\n", l, sum["rios"]
                    printf "archon_unit_io_writes_total%s %.0f\n", l, sum["wios"]
                }' "$dir/io.stat"
            [ -r "$dir/io.pressure" ] && psi "archon_unit_io_stalled_seconds_total$label" full "$dir/io.pressure"
        done
    } > "$out.tmp"
    mv "$out.tmp" "$out"
    sleep 15
done
