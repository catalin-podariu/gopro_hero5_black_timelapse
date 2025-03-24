#!/usr/bin/env bash
set -euo pipefail

########################################
# CONFIG & USAGE
########################################
usage() {
  cat <<EOF
Usage: $0 {hour|day}

Collects:
  1) system journal logs for the last hour/day
  2) kernel logs for the last hour/day
  3) NetworkManager logs for the last hour/day
  4) lines from each file in /home/timelapse/logs that fall in the range:
        [NOW - 1 hour, NOW] or [NOW - 24 hours, NOW]
     plus any subsequent lines without a timestamp, until the next out-of-range
     timestamp or EOF.
EOF
  exit 1
}

if [ $# -ne 1 ]; then
  usage
fi

MODE="$1"
OUTPUT_DIR="/home/timelapse/debug_logs"
PY_LOG_DIR="/home/timelapse/logs"

NOW_EPOCH=$(date +%s)        # current epoch time
case "$MODE" in
  hour)
    JOURNAL_SINCE="-1 hour"
    SECONDS_RANGE=$(( 60 * 60 ))     # 1 hour in seconds
    ;;
  day)
    JOURNAL_SINCE="-1 day"
    SECONDS_RANGE=$(( 24 * 60 * 60 ))  # 24 hours in seconds
    ;;
  *)
    usage
    ;;
esac

# The earliest time we want to keep
START_EPOCH=$(( NOW_EPOCH - SECONDS_RANGE ))

echo "Collecting logs for the last $MODE into $OUTPUT_DIR ..."
mkdir -p "$OUTPUT_DIR"

########################################
# 1) COLLECT JOURNAL LOGS (SYSTEM, KERNEL, NM)
########################################

# Systemd journal (all system messages):
if ! sudo journalctl --since "$JOURNAL_SINCE" > "$OUTPUT_DIR/system_journal.log" 2>/dev/null; then
  echo "Warning: Failed to collect system journal logs."
fi

# Kernel messages (dmesg):
if ! sudo journalctl -k --since "$JOURNAL_SINCE" > "$OUTPUT_DIR/kernel_journal.log" 2>/dev/null; then
  echo "Warning: Failed to collect kernel logs."
fi

# NetworkManager logs:
if ! sudo journalctl -u NetworkManager --since "$JOURNAL_SINCE" > "$OUTPUT_DIR/network_manager.log" 2>/dev/null; then
  echo "Warning: Failed to collect NetworkManager logs."
fi


########################################
# 2) PARSE PYTHON / CUSTOM LOG FILES
#    We'll keep lines from START_EPOCH..NOW_EPOCH, plus subsequent lines until
#    we see a timestamp outside that range.
########################################

if [ ! -d "$PY_LOG_DIR" ]; then
  echo "No $PY_LOG_DIR folder found; skipping custom logs."
  exit 0
fi

# We'll parse each file in $PY_LOG_DIR with an AWK script:
AWK_SCRIPT='
########################################################################
# This AWK script looks for lines containing one of two date formats:
#   1) Syslog style:  "Feb 02 16:12:18" (month day HH:MM:SS)
#                     We assume current YEAR = 2025 or the system year.
#   2) ISO style:     "2025-02-02 16:12:18" or "2025-02-02 16:12:18,289"
#
# We convert these to epoch (seconds since 1970) using gawk mktime().
# Then we decide if the parsed date is within [START_EPOCH..END_EPOCH].
# We toggle a boolean inRange.  For lines without a parseable date, we
# include them if inRange is still true (meaning "between two in-range timestamps").
#
# For syslog-like "Jan 25 09:44:59", we guess YEAR.  We default to the
# current system year, but you can force YEAR=2025 if all logs are from 2025.
########################################################################

function monthNum(m) {
  # Convert a three-letter month to a number
  # If we might see uppercase or capitalized, consider tolower(m)
  m = tolower(m)
  if (m == "jan") return 1
  if (m == "feb") return 2
  if (m == "mar") return 3
  if (m == "apr") return 4
  if (m == "may") return 5
  if (m == "jun") return 6
  if (m == "jul") return 7
  if (m == "aug") return 8
  if (m == "sep") return 9
  if (m == "oct") return 10
  if (m == "nov") return 11
  if (m == "dec") return 12
  return 0
}

BEGIN {
  inRange = 0
  # AWK variables come from -v
  startEpoch = START_E
  endEpoch   = END_E
  # Attempt to guess "current year" for syslog timestamps
  # If you know all are from 2025, set yearGuess=2025
  # Otherwise, do yearGuess = strftime("%Y")
  yearGuess = strftime("%Y")
}

{
  # Attempt to parse date from line. Priority:
  # 1) ISO 8601: 2025-02-02 16:12:18 or with optional ,xxx
  # 2) Syslog:   Feb 02 16:12:18

  epoch = -1

  # Pattern 1: ISO-like "2025-01-27 18:19:49" (with optional fractional seconds)
  # e.g.  ^2025-01-27 18:19:49,283  or  2025-01-27 18:19:49
  if (match($0, /^([0-9]{4})-([0-9]{2})-([0-9]{2})[ T]([0-9]{2}):([0-9]{2}):([0-9]{2})/, arr)) {
    # arr[1]=YYYY, arr[2]=MM, arr[3]=DD, arr[4]=HH, arr[5]=MM, arr[6]=SS
    year  = arr[1]
    month = arr[2]
    day   = arr[3]
    hour  = arr[4]
    minute= arr[5]
    second= arr[6]

    epoch = mktime(year " " month " " day " " hour " " minute " " second)
  }
  else if (match($0, /^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) +([0-9]{1,2}) +([0-9]{2}):([0-9]{2}):([0-9]{2})/, arr)) {
    # Syslog style: "Feb 02 16:12:18"
    # arr[1]=MonthName, arr[2]=Day, arr[3]=Hour, arr[4]=Min, arr[5]=Sec
    # We guess the year
    mon = monthNum(arr[1])
    day = arr[2]
    hour= arr[3]
    minute = arr[4]
    second = arr[5]
    epoch = mktime(yearGuess " " mon " " day " " hour " " minute " " second)
  }

  if (epoch >= 0) {
    # We got a valid date
    if (epoch >= startEpoch && epoch <= endEpoch) {
      inRange = 1
    } else {
      inRange = 0
    }
  }

  if (inRange == 1) {
    print $0
  }
}
'

echo "Parsing each log in '$PY_LOG_DIR' to keep lines from $(date -d "@$START_EPOCH") to now..."

for file in "$PY_LOG_DIR"/*; do
  # Skip if not a regular file
  [ -f "$file" ] || continue

  base=$(basename "$file")
  out="$OUTPUT_DIR/$base"

  echo "  -> Slicing $base into $out"

  # Use gawk with -v to pass shell variables into the script
  gawk -v START_E="$START_EPOCH" -v END_E="$NOW_EPOCH" "$AWK_SCRIPT" "$file" > "$out" || {
    echo "Warning: AWK processing failed for $file"
  }
done

echo "Done. Check $OUTPUT_DIR for the resulting logs."

