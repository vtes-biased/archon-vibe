import json
import os
import urllib.error
import urllib.request

GRAFANA = "https://vtesbiased.grafana.net"
FOLDER = "archon"
GROUP = "archon"
RECEIVER = "archon-discord"
HOST = 'instance="archon.vekn.net"'
UNITS = 'name=~"archon-.*|nginx.service|postgresql@.*|fluent-bit.*"'
SHOWN_UNITS = f'{UNITS}, name!~"fluent-bit.*"'
SHOWN = 'unit!~"fluent-bit.*"'

RULES = [
    (
        "archon-unit-down",
        "A production unit is down",
        f'max by (name) (node_systemd_unit_state{{{HOST}, {UNITS}, state=~"failed|inactive"}})',
        "gt",
        0,
        "3m",
        "OK",
    ),
    (
        "archon-unit-restarting",
        "A production unit is restart-looping",
        f"increase(node_systemd_service_restart_total{{{HOST}, {UNITS}}}[30m])",
        "gt",
        3,
        "0s",
        "OK",
    ),
    (
        "archon-memory-low",
        "Production is short of memory",
        f"node_memory_MemAvailable_bytes{{{HOST}}} / node_memory_MemTotal_bytes{{{HOST}}}",
        "lt",
        0.1,
        "10m",
        "OK",
    ),
    (
        "archon-memory-stalled",
        "Production is thrashing",
        f"rate(node_pressure_memory_stalled_seconds_total{{{HOST}}}[5m])",
        "gt",
        0.1,
        "5m",
        "OK",
    ),
    (
        "archon-logs-dropped",
        "Production's log or metric shipping is failing",
        f"increase(fluentbit_output_retries_failed_total{{{HOST}}}[15m])",
        "gt",
        0,
        "0s",
        "OK",
    ),
    (
        "archon-host-silent",
        "Production stopped reporting",
        f"count_over_time(node_uname_info{{{HOST}}}[10m])",
        "lt",
        1,
        "0s",
        "Alerting",
    ),
]


PROM = {"type": "prometheus", "uid": "grafanacloud-prom"}
LOKI = {"type": "loki", "uid": "grafanacloud-logs"}
LOGS = f'{{host="archon.vekn.net", {SHOWN}, unit=~"$unit", level=~"$level"}} |~ "(?i)$search"'
RATE = "$__rate_interval"
LEVEL_COLORS = {
    "error": "red",
    "warning": "orange",
    "notice": "blue",
    "info": "green",
    "debug": "text",
}


def colors(by: dict[str, str]) -> list[dict]:
    return [
        {
            "matcher": {"id": "byName", "options": name},
            "properties": [
                {"id": "color", "value": {"mode": "fixed", "fixedColor": c}}
            ],
        }
        for name, c in by.items()
    ]


def ts(
    title, unit, *targets, stack=False, overrides=(), max_=None, bars=False, empty=None
):
    defaults = {
        "unit": unit,
        "noValue": empty,
        "min": 0,
        "custom": {
            "fillOpacity": 80 if bars else 18,
            "gradientMode": "opacity",
            "lineWidth": 1,
            "drawStyle": "bars" if bars else "line",
            "showPoints": "never",
            "stacking": {"mode": "normal" if stack else "none"},
        },
    }
    if max_ is not None:
        defaults["max"] = max_
    return {
        "type": "timeseries",
        "title": title,
        "datasource": targets[0][2] if len(targets[0]) > 2 else PROM,
        "fieldConfig": {"defaults": defaults, "overrides": list(overrides)},
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
        "targets": [
            {"refId": chr(65 + i), "expr": t[0], "legendFormat": t[1]}
            for i, t in enumerate(targets)
        ],
    }


def stat(title, unit, expr, steps, decimals=1):
    return {
        "type": "stat",
        "title": title,
        "datasource": PROM,
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "decimals": decimals,
                "color": {"mode": "thresholds"},
                "thresholds": {
                    "mode": "absolute",
                    "steps": [{"color": c, "value": v} for v, c in steps],
                },
            },
            "overrides": [],
        },
        "options": {
            "colorMode": "background",
            "graphMode": "area",
            "textMode": "value",
        },
        "targets": [{"refId": "A", "expr": expr}],
    }


def row(title):
    return {"type": "row", "title": title, "collapsed": False, "panels": []}


TX_BELOW = [
    {
        "matcher": {"id": "byRegexp", "options": "sent.*|write.*"},
        "properties": [{"id": "custom.transform", "value": "negative-Y"}],
    }
]
UNIT_STATE = {
    "type": "state-timeline",
    "title": "Units up",
    "datasource": PROM,
    "fieldConfig": {
        "defaults": {
            "mappings": [
                {
                    "type": "value",
                    "options": {
                        "0": {"text": "down", "color": "red"},
                        "1": {"text": "up", "color": "green"},
                    },
                }
            ],
            "color": {"mode": "thresholds"},
            "thresholds": {
                "mode": "absolute",
                "steps": [
                    {"color": "red", "value": None},
                    {"color": "green", "value": 1},
                ],
            },
        },
        "overrides": [],
    },
    "options": {
        "showValue": "never",
        "mergeValues": True,
        "legend": {"showLegend": False},
    },
    "targets": [
        {
            "refId": "A",
            "expr": f'node_systemd_unit_state{{{HOST}, {SHOWN_UNITS}, state="active"}}',
            "legendFormat": "{{name}}",
        }
    ],
}
LOG_PANEL = {
    "type": "logs",
    "title": "Logs",
    "datasource": LOKI,
    "options": {
        "showTime": True,
        "wrapLogMessage": True,
        "sortOrder": "Descending",
        "enableLogDetails": True,
        "dedupStrategy": "none",
    },
    "targets": [{"refId": "A", "expr": LOGS}],
}

BACKEND = '{host="archon.vekn.net", unit="archon-backend.service"}'


def push_failures(title, subject, pattern, labels):
    expr = (
        f"sum by ({labels}) (count_over_time({BACKEND}"
        f' |= "VEKN push failed: {subject}=" | regexp `{pattern}` [2h]))'
    )
    return {
        "type": "table",
        "title": title,
        "datasource": LOKI,
        "fieldConfig": {"defaults": {"noValue": "Nothing failing"}, "overrides": []},
        "options": {"showHeader": True, "cellHeight": "sm"},
        "targets": [
            {
                "refId": "A",
                "expr": expr,
                "queryType": "instant",
                "instant": True,
                "range": False,
                "format": "table",
            }
        ],
        "transformations": [
            {
                "id": "organize",
                "options": {
                    "excludeByName": {"Time": True},
                    "renameByName": {"Value": "attempts (2h)"},
                },
            }
        ],
    }


CPU_BUSY = f'1 - avg(rate(node_cpu_seconds_total{{{HOST}, mode="idle"}}[5m]))'
MEM_AVAIL = (
    f"node_memory_MemAvailable_bytes{{{HOST}}} / node_memory_MemTotal_bytes{{{HOST}}}"
)
SWAP_USED = (
    f"node_memory_SwapTotal_bytes{{{HOST}}} - node_memory_SwapFree_bytes{{{HOST}}}"
)
ROOT_FS = f'{HOST}, mountpoint="/"'
LAYOUT = [
    (row("Overview"), 24, 1),
    (
        stat(
            "Uptime",
            "s",
            f"time() - node_boot_time_seconds{{{HOST}}}",
            [(None, "blue")],
            0,
        ),
        4,
        4,
    ),
    (
        stat(
            "CPU busy",
            "percentunit",
            CPU_BUSY,
            [(None, "green"), (0.7, "orange"), (0.9, "red")],
        ),
        4,
        4,
    ),
    (
        stat(
            "Memory available",
            "percentunit",
            MEM_AVAIL,
            [(None, "red"), (0.1, "orange"), (0.25, "green")],
        ),
        4,
        4,
    ),
    (
        stat(
            "Swap used",
            "bytes",
            SWAP_USED,
            [(None, "green"), (256e6, "orange"), (1e9, "red")],
        ),
        4,
        4,
    ),
    (
        stat(
            "Memory stalled",
            "percentunit",
            f"rate(node_pressure_memory_stalled_seconds_total{{{HOST}}}[5m])",
            [(None, "green"), (0.02, "orange"), (0.1, "red")],
            2,
        ),
        4,
        4,
    ),
    (
        stat(
            "Disk used",
            "percentunit",
            f"1 - node_filesystem_avail_bytes{{{ROOT_FS}}} / node_filesystem_size_bytes{{{ROOT_FS}}}",
            [(None, "green"), (0.8, "orange"), (0.9, "red")],
        ),
        4,
        4,
    ),
    (row("CPU"), 24, 1),
    (
        ts(
            "CPU by mode",
            "percentunit",
            (
                f'sum by (mode) (rate(node_cpu_seconds_total{{{HOST}, mode!="idle"}}[{RATE}]))',
                "{{mode}}",
            ),
            stack=True,
            max_=1,
        ),
        8,
        8,
    ),
    (
        ts(
            "CPU per unit",
            "percentunit",
            (
                f"rate(archon_unit_cpu_seconds_total{{{HOST}, {SHOWN}}}[{RATE}])",
                "{{unit}}",
            ),
            stack=True,
        ),
        8,
        8,
    ),
    (
        ts(
            "Load and CPU pressure",
            "short",
            (f"node_load1{{{HOST}}}", "load 1m"),
            (f"node_load5{{{HOST}}}", "load 5m"),
            (
                f"rate(node_pressure_cpu_waiting_seconds_total{{{HOST}}}[{RATE}])",
                "CPU waiting",
            ),
        ),
        8,
        8,
    ),
    (row("Memory"), 24, 1),
    (
        ts(
            "Host memory",
            "bytes",
            (
                f"node_memory_MemTotal_bytes{{{HOST}}} - node_memory_MemAvailable_bytes{{{HOST}}}",
                "used",
            ),
            (
                f"node_memory_Cached_bytes{{{HOST}}} + node_memory_Buffers_bytes{{{HOST}}}",
                "cache",
            ),
            (f"node_memory_MemAvailable_bytes{{{HOST}}}", "available"),
            (SWAP_USED, "swap used"),
        ),
        8,
        8,
    ),
    (
        ts(
            "Memory per unit",
            "bytes",
            (f"archon_unit_memory_bytes{{{HOST}, {SHOWN}}}", "{{unit}}"),
            stack=True,
        ),
        8,
        8,
    ),
    (
        ts(
            "Swap per unit",
            "bytes",
            (f"archon_unit_swap_bytes{{{HOST}, {SHOWN}}}", "{{unit}}"),
            stack=True,
        ),
        8,
        8,
    ),
    (
        ts(
            "Memory pressure",
            "percentunit",
            (
                f"rate(node_pressure_memory_stalled_seconds_total{{{HOST}}}[{RATE}])",
                "all stalled",
            ),
            (
                f"rate(node_pressure_memory_waiting_seconds_total{{{HOST}}}[{RATE}])",
                "some waiting",
            ),
            (
                f"rate(node_vmstat_pgmajfault{{{HOST}}}[{RATE}]) / 1000",
                "major faults (k/s)",
            ),
        ),
        12,
        8,
    ),
    (
        ts(
            "Memory stall per unit",
            "percentunit",
            (
                f"rate(archon_unit_memory_stalled_seconds_total{{{HOST}, {SHOWN}}}[{RATE}])",
                "{{unit}}",
            ),
        ),
        12,
        8,
    ),
    (row("Network and disk"), 24, 1),
    (
        ts(
            "Network",
            "Bps",
            (
                f'rate(node_network_receive_bytes_total{{{HOST}, device!="lo"}}[{RATE}])',
                "received",
            ),
            (
                f'rate(node_network_transmit_bytes_total{{{HOST}, device!="lo"}}[{RATE}])',
                "sent",
            ),
            overrides=TX_BELOW,
        ),
        8,
        8,
    ),
    (
        ts(
            "Disk throughput",
            "Bps",
            (f"rate(node_disk_read_bytes_total{{{HOST}}}[{RATE}])", "read"),
            (f"rate(node_disk_written_bytes_total{{{HOST}}}[{RATE}])", "write"),
            overrides=TX_BELOW,
        ),
        8,
        8,
    ),
    (
        ts(
            "I/O pressure",
            "percentunit",
            (
                f"rate(node_pressure_io_stalled_seconds_total{{{HOST}}}[{RATE}])",
                "all stalled",
            ),
            (
                f"rate(node_pressure_io_waiting_seconds_total{{{HOST}}}[{RATE}])",
                "some waiting",
            ),
        ),
        8,
        8,
    ),
    (
        ts(
            "Disk throughput per unit",
            "Bps",
            (
                f"rate(archon_unit_io_read_bytes_total{{{HOST}, {SHOWN}}}[{RATE}])",
                "read {{unit}}",
            ),
            (
                f"rate(archon_unit_io_written_bytes_total{{{HOST}, {SHOWN}}}[{RATE}])",
                "write {{unit}}",
            ),
            overrides=TX_BELOW,
        ),
        8,
        8,
    ),
    (
        ts(
            "Disk operations per unit",
            "iops",
            (
                f"rate(archon_unit_io_reads_total{{{HOST}, {SHOWN}}}[{RATE}])",
                "read {{unit}}",
            ),
            (
                f"rate(archon_unit_io_writes_total{{{HOST}, {SHOWN}}}[{RATE}])",
                "write {{unit}}",
            ),
            overrides=TX_BELOW,
        ),
        8,
        8,
    ),
    (
        ts(
            "I/O stall per unit",
            "percentunit",
            (
                f"rate(archon_unit_io_stalled_seconds_total{{{HOST}, {SHOWN}}}[{RATE}])",
                "{{unit}}",
            ),
        ),
        8,
        8,
    ),
    (row("Services"), 24, 1),
    (UNIT_STATE, 16, 7),
    (
        ts(
            "Restarts",
            "none",
            (
                f"increase(node_systemd_service_restart_total{{{HOST}, {SHOWN_UNITS}}}[1h]) > 0",
                "{{name}}",
            ),
            bars=True,
            empty="No restarts",
        ),
        8,
        7,
    ),
    (row("VEKN push"), 24, 1),
    (
        push_failures(
            "Failing tournaments",
            "tournament",
            r"tournament=(?P<tournament>\S+) vekn_event=(?P<vekn_event>\S+) reason=(?P<reason>.*)",
            "tournament, vekn_event, reason",
        ),
        24,
        8,
    ),
    (
        push_failures(
            "Failing members",
            "member",
            r"member=(?P<member>\S+) reason=(?P<reason>.*)",
            "member, reason",
        ),
        24,
        6,
    ),
    (row("Logs"), 24, 1),
    (
        ts(
            "Log volume by level",
            "short",
            (f"sum by (level) (count_over_time({LOGS} [$__auto]))", "{{level}}", LOKI),
            stack=True,
            bars=True,
            overrides=colors(LEVEL_COLORS),
        ),
        24,
        6,
    ),
    (LOG_PANEL, 24, 16),
]


def dashboard() -> dict:
    panels, x, y, line = [], 0, 0, 0
    for i, (panel, w, h) in enumerate(LAYOUT):
        if x + w > 24:
            x, y = 0, y + line
            line = 0
        panels.append(
            {**panel, "id": i + 1, "gridPos": {"x": x, "y": y, "w": w, "h": h}}
        )
        x, line = x + w, max(line, h)
    variables = [
        {
            "name": name,
            "label": name.capitalize(),
            "type": "query",
            "datasource": LOKI,
            "query": {
                "label": name,
                "stream": f'{{host="archon.vekn.net", {SHOWN}}}',
                "type": 1,
            },
            "includeAll": True,
            "multi": True,
            "allValue": ".+",
            "current": {"text": "All", "value": "$__all"},
            "refresh": 2,
        }
        for name in ("unit", "level")
    ]
    variables.append(
        {
            "name": "search",
            "label": "User, tournament or text",
            "type": "textbox",
            "query": "",
            "current": {"text": "", "value": ""},
        }
    )
    return {
        "uid": "archon-prod",
        "title": "Archon production",
        "tags": ["archon"],
        "time": {"from": "now-24h", "to": "now"},
        "refresh": "1m",
        "templating": {"list": variables},
        "panels": panels,
    }


def call(method: str, path: str, body: dict | None = None) -> tuple[int, str]:
    request = urllib.request.Request(
        GRAFANA + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {os.environ['GRAFANA_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def upsert(path: str, uid: str, body: dict) -> None:
    status, text = call("PUT", f"{path}/{uid}", body)
    if status == 404:
        status, text = call("POST", path, body)
    if status >= 300:
        raise SystemExit(f"{path}/{uid}: {status} {text}")
    print(f"{path}/{uid}: {status}")


def rule(uid, title, expr, op, threshold, pending, no_data) -> dict:
    return {
        "uid": uid,
        "title": title,
        "folderUID": FOLDER,
        "ruleGroup": GROUP,
        "condition": "C",
        "data": [
            {
                "refId": "A",
                "relativeTimeRange": {"from": 900, "to": 0},
                "datasourceUid": "grafanacloud-prom",
                "model": {"refId": "A", "expr": expr, "instant": True},
            },
            {
                "refId": "C",
                "relativeTimeRange": {"from": 0, "to": 0},
                "datasourceUid": "__expr__",
                "model": {
                    "refId": "C",
                    "type": "threshold",
                    "expression": "A",
                    "conditions": [{"evaluator": {"type": op, "params": [threshold]}}],
                },
            },
        ],
        "for": pending,
        "noDataState": no_data,
        "execErrState": "Error",
        "annotations": {"summary": title},
        "notification_settings": {"receiver": RECEIVER},
    }


def main() -> None:
    status, text = call("POST", "/api/folders", {"uid": FOLDER, "title": "Archon"})
    if status >= 300 and status not in (409, 412):
        raise SystemExit(f"folder: {status} {text}")
    if webhook := os.environ.get("DISCORD_WEBHOOK"):
        upsert(
            "/api/v1/provisioning/contact-points",
            RECEIVER,
            {
                "uid": RECEIVER,
                "name": RECEIVER,
                "type": "discord",
                "settings": {"url": webhook, "use_discord_username": False},
            },
        )
    status, text = call(
        "POST",
        "/api/dashboards/db",
        {
            "dashboard": dashboard(),
            "folderUid": FOLDER,
            "overwrite": True,
        },
    )
    if status >= 300:
        raise SystemExit(f"dashboard: {status} {text}")
    print("dashboard archon-prod")
    url = "https://grafana.com/api/dashboards/1860/revisions/latest/download"
    with urllib.request.urlopen(url, timeout=30) as response:
        node_full = json.load(response)
    status, text = call(
        "POST",
        "/api/dashboards/import",
        {
            "dashboard": node_full,
            "overwrite": True,
            "folderUid": FOLDER,
            "inputs": [
                {
                    "name": "DS_PROMETHEUS",
                    "type": "datasource",
                    "pluginId": "prometheus",
                    "value": "grafanacloud-prom",
                }
            ],
        },
    )
    if status >= 300:
        raise SystemExit(f"node exporter full: {status} {text}")
    print(f"dashboard {json.loads(text).get('uid')} (Node Exporter Full)")
    status, text = call(
        "PUT",
        f"/api/v1/provisioning/folder/{FOLDER}/rule-groups/{GROUP}",
        {"interval": 60, "rules": [rule(*spec) for spec in RULES]},
    )
    if status >= 300:
        raise SystemExit(f"rule group: {status} {text}")
    print("rule group: every 60s")


if __name__ == "__main__":
    main()
