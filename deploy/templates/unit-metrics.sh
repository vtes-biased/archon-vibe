#!/bin/sh
set -u
out=/var/lib/fluent-bit/textfile/units.prom
units="archon-backend archon-public-api archon-bot nginx postgresql@17-main fluent-bit"

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
        for unit in $units; do
            dir=/sys/fs/cgroup$(systemctl show -P ControlGroup "$unit.service")
            [ "$dir" = /sys/fs/cgroup ] && continue
            label="{unit=\"$unit.service\"}"
            [ -r "$dir/memory.current" ] && echo "archon_unit_memory_bytes$label $(cat "$dir/memory.current")"
            [ -r "$dir/memory.swap.current" ] && echo "archon_unit_swap_bytes$label $(cat "$dir/memory.swap.current")"
            [ -r "$dir/cpu.stat" ] && awk -v l="$label" '$1 == "usage_usec" { printf "archon_unit_cpu_seconds_total%s %.6f\n", l, $2 / 1e6 }' "$dir/cpu.stat"
            [ -r "$dir/memory.pressure" ] && psi "archon_unit_memory_stalled_seconds_total$label" full "$dir/memory.pressure"
        done
        :
    } > "$out.tmp" && mv "$out.tmp" "$out"
    sleep 15
done
