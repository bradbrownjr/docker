-- Lua script to transform syslog to LogWard format

-- Syslog severity to LogWard level mapping
local severity_map = {
    [0] = "critical",  -- Emergency
    [1] = "critical",  -- Alert
    [2] = "critical",  -- Critical
    [3] = "error",     -- Error
    [4] = "warn",      -- Warning
    [5] = "info",      -- Notice
    [6] = "info",      -- Informational
    [7] = "debug"      -- Debug
}

function transform_syslog(tag, timestamp, record)
    -- Extract severity from priority (pri = facility * 8 + severity)
    local pri = tonumber(record["pri"]) or 14  -- Default to info (facility 1, severity 6)
    local severity = pri % 8
    local facility = math.floor(pri / 8)
    
    -- Map severity to LogWard level
    record["level"] = severity_map[severity] or "info"
    
    -- Ensure service is set
    if not record["service"] or record["service"] == "" then
        record["service"] = record["ident"] or record["host"] or "syslog"
    end
    
    -- Ensure message is set
    if not record["message"] or record["message"] == "" then
        record["message"] = "No message"
    end
    
    -- Add metadata
    record["metadata"] = {
        facility = facility,
        severity = severity,
        ident = record["ident"],
        pid = record["pid"],
        source = "syslog"
    }
    
    -- Clean up intermediate fields
    record["pri"] = nil
    record["ident"] = nil
    record["pid"] = nil
    record["host"] = nil
    
    return 1, timestamp, record
end
