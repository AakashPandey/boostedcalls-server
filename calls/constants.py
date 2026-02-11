"""
Constants for the calls app.
"""

# Maximum number of concurrent active calls per user.
MAX_PENDING_CALLS = 2

# Calls stuck in pending/queued for longer than this are considered stale (seconds).
STALE_CALL_THRESHOLD_SECONDS = 10 * 60  # 10 minutes

# Calls queued longer than this get a one-shot Vapi sync (seconds).
STALE_QUEUED_SYNC_SECONDS = 2 * 60  # 2 minutes

# Active (non-terminal) statuses – used for rate-limiting & cleanup queries.
ACTIVE_STATUSES = [
    "pending",
    "queued",
    "initiated",
    "ringing",
    "in-progress",
]

# Statuses considered stale-eligible.
STALE_ELIGIBLE_STATUSES = ["pending", "queued"]

# Terminal statuses – once a call reaches one of these it cannot transition further.
TERMINAL_STATUSES = [
    "completed",
    "failed",
    "cancelled",
    "no-answer",
    "busy",
    "voicemail",
]

# Numeric ordering for lifecycle validation.
# Terminal states all share order 10 so they are always reachable.
STATUS_ORDER: dict[str, int] = {
    "pending": 0,
    "queued": 1,
    "initiated": 2,
    "ringing": 3,
    "in-progress": 4,
    "completed": 10,
    "failed": 10,
    "cancelled": 10,
    "no-answer": 10,
    "busy": 10,
    "voicemail": 10,
}
