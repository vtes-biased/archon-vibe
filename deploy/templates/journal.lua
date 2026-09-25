-- journald's PRIORITY is a number; the level label is the keyword Alloy emits for it
local LEVELS = { "emerg", "alert", "crit", "error", "warning", "notice", "info", "debug" }

function journal(tag, timestamp, record)
    return 2, timestamp, {
        unit = record["_SYSTEMD_UNIT"],
        tag = record["SYSLOG_IDENTIFIER"],
        level = LEVELS[(tonumber(record["PRIORITY"]) or 6) + 1],
        message = record["MESSAGE"],
    }
end
