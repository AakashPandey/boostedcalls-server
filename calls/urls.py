"""
URL routes for the calls app.

Mounted under ``/api/`` by config/urls.py.
"""

from django.urls import path

from calls.views import calls as call_views
from calls.views import contacts as contact_views
from calls.views import call_scripts as script_views

app_name = "calls"

urlpatterns = [
    # ── Calls ──────────────────────────────────────────────────────────────
    path("calls/", call_views.call_list_create, name="call-list-create"),
    path("calls/webhook/", call_views.vapi_webhook, name="vapi-webhook"),
    path("calls/pending-count/", call_views.call_pending_count, name="call-pending-count"),
    path("calls/stats/", call_views.call_dashboard_stats, name="call-dashboard-stats"),
    path("calls/<uuid:call_id>/cancel/", call_views.call_cancel, name="call-cancel"),
    path("calls/<uuid:call_id>/sync/", call_views.call_sync, name="call-sync"),
    path("calls/<uuid:call_id>/", call_views.call_detail, name="call-detail"),

    # ── Contacts ──────────────────────────────────────────────────────────
    path("contacts/", contact_views.contact_list_create, name="contact-list-create"),
    path("contacts/<uuid:contact_id>/", contact_views.contact_detail, name="contact-detail"),

    # ── Call Scripts ──────────────────────────────────────────────────────
    path("scripts/", script_views.script_list_create, name="script-list-create"),
    path("scripts/<uuid:script_id>/", script_views.script_detail, name="script-detail"),
]
