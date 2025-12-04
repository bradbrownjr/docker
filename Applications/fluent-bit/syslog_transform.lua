-- Lua script to transform syslog to LogWard format

local severity_map = {
    [0] = "critical", [1] = "critical", [2] = "critical",
    [3] = "error", [4] = "warn", [5] = "info", [6] = "info", [7] = "debug"
}

function transform_syslog(tag, timestamp, record)
    -- Extract severity from priority
    local pri = tonumber(record["pri"]) or 14
    local severity = pri % 8
    local facility = math.floor(pri / 8)
    
    -- Set level
    record["level"] = severity_map[severity] or "info"
    
    -- Set service from ident, host, or default
    if record["ident"] and record["ident"] ~= "" then
        record["service"] = record["ident"]
    elseif record["host"] and record["host"] ~= "" then
        record["service"] = record["host"]
    else
        record["service"] = "syslog"
    end
    
    -- IMPORTANT: Get the actual message content
    -- The message might be in different fields depending on the parser
    local msg = nil
    if record["message"] and record["message"] ~= "" then
        msg = record["message"]
    elseif record["msg"] and record["msg"] ~= "" then
        msg = record["msg"]
    elseif record["log"] and record["log"] ~= "" then
        msg = record["log"]
    end
    
    -- If still no message, try to build one from available fields
    if not msg or msg == "" then
        -- For tail input, the whole line might be in a different field
        for k, v in pairs(record) do
            if type(v) == "string" and k ~= "pri" and k ~= "time" and k ~= "host" and k ~= "ident" and k ~= "pid" and k ~= "level" and k ~= "service" then
                if v ~= "" and string.len(v) > 10 then
                    msg = v
                    break
                end
            end
        end
    end
    
    record["message"] = msg or "syslog entry"
    
    -- Generate ISO 8601 timestamp from Fluent Bit timestamp
    -- The 'timestamp' parameter is the actual time in seconds
    record["time"] = os.date("!%Y-%m-%dT%H:%M:%SZ", math.floor(timestamp))
    
    -- Add metadata
    record["metadata"] = {
        facility = facility,
        severity = severity,
        ident = record["ident"],
        pid = record["pid"],
        original_host = record["host"],
        source = "syslog"
    }
    
    -- Clean up intermediate fields (don't send to LogWard)
    record["pri"] = nil
    record["ident"] = nil
    record["pid"] = nil
    record["host"] = nil
    record["msg"] = nil
    record["log"] = nil
    
    return 1, timestamp, record
end
