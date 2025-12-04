-- Lua script to transform syslog to LogWard format

local severity_map = {
    [0] = "critical", [1] = "critical", [2] = "critical",
    [3] = "error", [4] = "warn", [5] = "info", [6] = "info", [7] = "debug"
}

-- Helper function to extract just the IP from source_ip
-- Fluent Bit may return "udp://10.6.26.1:22156" format
local function extract_ip(source)
    if not source or source == "" then
        return nil
    end
    -- Try to match IP from "protocol://ip:port" format
    local ip = string.match(source, "://([%d%.]+):")
    if ip then
        return ip
    end
    -- Try to match IP from "ip:port" format
    ip = string.match(source, "^([%d%.]+):")
    if ip then
        return ip
    end
    -- Try to match bare IP
    ip = string.match(source, "^(%d+%.%d+%.%d+%.%d+)$")
    if ip then
        return ip
    end
    -- Return as-is if no pattern matches
    return source
end

function transform_syslog(tag, timestamp, record)
    -- Extract severity from priority
    local pri = tonumber(record["pri"]) or 14
    local severity = pri % 8
    local facility = math.floor(pri / 8)
    
    -- Set level
    record["level"] = severity_map[severity] or "info"
    
    -- Try to parse hostname from the raw message (RFC 3164 format)
    -- Format: "Dec  4 14:55:09 Tower kernel: message"
    local parsed_host = nil
    local program = nil
    local raw_msg = record["message"] or record["msg"] or ""
    
    -- Match RFC 3164: "Mon DD HH:MM:SS hostname tag: message"
    local host_match = string.match(raw_msg, "^%w+%s+%d+%s+%d+:%d+:%d+%s+(%S+)%s+")
    if host_match then
        parsed_host = host_match
        -- Also try to get the program/tag
        program = string.match(raw_msg, "^%w+%s+%d+%s+%d+:%d+:%d+%s+%S+%s+([^:%[]+)")
    end
    
    -- Extract clean IP from source_ip field
    local clean_source_ip = extract_ip(record["source_ip"])
    
    -- Determine service name with priority:
    -- 1. Parsed hostname from message (most reliable for local syslog)
    -- 2. Source IP from network connection (for remote syslog)
    -- 3. Host field from syslog header
    -- 4. Fallback to "syslog"
    if parsed_host and parsed_host ~= "" then
        record["service"] = parsed_host
        record["_program"] = program
    elseif clean_source_ip then
        -- Use source IP for network syslog (firewall, switches, etc.)
        record["service"] = clean_source_ip
        record["_program"] = record["ident"]
    elseif record["host"] and record["host"] ~= "" then
        record["service"] = record["host"]
        record["_program"] = record["ident"]
    else
        record["service"] = "syslog"
        record["_program"] = record["ident"]
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
        source = "syslog",
        program = record["_program"] or record["ident"],
        facility = facility,
        severity = severity,
        parsed_host = parsed_host,
        source_ip = clean_source_ip
    }
    
    -- Clean up intermediate fields (don't send to LogWard)
    record["pri"] = nil
    record["ident"] = nil
    record["pid"] = nil
    record["host"] = nil
    record["msg"] = nil
    record["log"] = nil
    record["source_ip"] = nil
    record["_program"] = nil
    
    return 1, timestamp, record
end
