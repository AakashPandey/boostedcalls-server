"""
Views package for the calls app.

Re-exports every view so ``from calls import views`` / ``calls.views.xyz``
continues to work (e.g. in urls.py).
"""

# Calls
from calls.views.calls import (  # noqa: F401
    call_cancel,
    call_detail,
    call_list_create,
    call_pending_count,
    call_sync,
    vapi_webhook,
)

# Contacts
from calls.views.contacts import (  # noqa: F401
    contact_detail,
    contact_list_create,
)

# Call Scripts
from calls.views.call_scripts import (  # noqa: F401
    script_detail,
    script_list_create,
)
