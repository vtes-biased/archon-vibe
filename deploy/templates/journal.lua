-- journald's PRIORITY is a number; the level label is the keyword Alloy emits for it
local LEVELS = { "emerg", "alert", "crit", "error", "warning", "notice", "info", "debug" }

local function mask(message)
    if type(message) ~= "string" then
        return message
    end
    for _, param in ipairs({ "token", "code", "state" }) do
        message = message:gsub("([?&]" .. param .. "=)[^&%s\"]+", "%1***")
    end
    return message
end

function journal(tag, timestamp, record)
    return 2, timestamp, {
        unit = record["_SYSTEMD_UNIT"],
        tag = record["SYSLOG_IDENTIFIER"],
        level = LEVELS[(tonumber(record["PRIORITY"]) or 6) + 1],
        message = mask(record["MESSAGE"]),
    }
end
