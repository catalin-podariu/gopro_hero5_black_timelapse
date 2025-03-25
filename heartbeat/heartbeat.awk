#!/usr/bin/awk -f
###############################################################################
# heartbeat.awk (no debug/logging)
#
# Outputs a single character based on the last minute's worth of log lines:
#   "?" => OFFLINE
#   "|" => RESTART
#   "@" => PHOTO
#   "+" => WOL
#   "-" => none of the above
#
# Assumes each log line starts with a timestamp "YYYY-MM-DD HH:MM:SS"
###############################################################################

BEGIN {
    # Get the current epoch
    cmd = "date +%s"
    cmd | getline nowEpoch
    close(cmd)

    # We'll treat "lastMinute" as now - 60 seconds
    lastMinute = nowEpoch - 60

    foundOffline  = 0
    foundRestart  = 0
    foundPhoto    = 0
    foundWol      = 0
}

{
    # Skip lines that do NOT start with "YYYY-MM-DD HH:MM:SS"
    if ($0 !~ /^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}/) {
        next
    }

    # Extract the date/time substring
    dateStr = substr($0, 1, 19)

    # Convert to epoch
    cmd = "date -d \"" dateStr "\" +%s"
    cmd | getline lineEpoch
    close(cmd)

    # If outside the last minute or in the future, skip
    if (lineEpoch < lastMinute || lineEpoch > nowEpoch) {
        next
    }

    # Convert entire line to uppercase for easy matching
    lineUpper = toupper($0)

    # Check for events, in no particular order yet
    if (index(lineUpper, "OFFLINE")  > 0) foundOffline = 1
    if (index(lineUpper, "RESTART")  > 0) foundRestart = 1
    if (index(lineUpper, "PHOTO NOW")    > 0) foundPhoto   = 1
    if (index(lineUpper, "WOL")      > 0) foundWol     = 1
}

END {
    # Priority check: OFFLINE -> RESTART -> PHOTO -> WOL -> none
    if (foundOffline) {
        print "?"
    } else if (foundRestart) {
        print "|"
    } else if (foundPhoto) {
        print "@"
    } else if (foundWol) {
        print "+"
    } else {
        print "-"
    }
}
