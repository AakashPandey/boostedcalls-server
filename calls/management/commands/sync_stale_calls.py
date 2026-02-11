"""
Management command to sync calls stuck in ``queued`` status for too long.

Polls Vapi for the latest state and reconciles the local DB row.
Run periodically (e.g. every 2–3 minutes via cron or Celery beat).

Usage::

    python manage.py sync_stale_calls
"""

from django.core.management.base import BaseCommand

from calls.services.calls import mark_stale_calls, sync_stale_queued_calls


class Command(BaseCommand):
    help = "Sync calls stuck in queued and mark timed-out calls as failed."

    def handle(self, *args, **options):
        # 1. Poll Vapi for calls queued > 2 min
        synced = sync_stale_queued_calls()
        self.stdout.write(f"Synced {synced} stale-queued call(s) via Vapi.")

        # 2. Fail calls stuck beyond the hard threshold (10 min)
        failed = mark_stale_calls()
        if failed:
            self.stdout.write(self.style.WARNING(f"Marked {failed} call(s) as failed (timed out)."))
        else:
            self.stdout.write("No timed-out calls found.")
