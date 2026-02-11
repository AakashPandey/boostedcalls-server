from django.db import models
import uuid
from django.conf import settings
from django.db import models


class CallScript(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bdc_call_scripts",
    )

    name = models.TextField()
    description = models.TextField(blank=True, null=True)
    custom_prompt = models.TextField(blank=True, null=True)
    first_message = models.TextField(blank=True, null=True)

    call_goals = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bdc_call_scripts"


class Contact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bdc_contacts",
    )

    name = models.TextField()
    phone = models.TextField()
    email = models.EmailField(blank=True, null=True)
    metadata = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bdc_contacts"


class CallStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    QUEUED = "queued", "Queued"
    INITIATED = "initiated", "Initiated"
    RINGING = "ringing", "Ringing"
    IN_PROGRESS = "in-progress", "In Progress"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    NO_ANSWER = "no-answer", "No Answer"
    BUSY = "busy", "Busy"
    VOICEMAIL = "voicemail", "Voicemail"


class CallOutcome(models.TextChoices):
    SUCCESS = "success", "Success"
    PARTIAL = "partial", "Partial"
    FAILED = "failed", "Failed"
    NOT_INTERESTED = "not_interested", "Not Interested"
    WRONG_NUMBER = "wrong_number", "Wrong Number"
    BUSY = "busy", "Busy"
    NO_ANSWER = "no_answer", "No Answer"
    VOICEMAIL = "voicemail", "Voicemail"
    LANGUAGE_BARRIER = "language_barrier", "Language Barrier"


class Call(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bdc_calls",
    )

    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        related_name="calls",
    )

    script = models.ForeignKey(
        CallScript,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="calls",
    )

    vapi_call_id = models.TextField(unique=True, blank=True, null=True)
    assistant_id = models.TextField()
    phone_number_id = models.TextField(blank=True, null=True)

    status = models.CharField(
        max_length=32,
        choices=CallStatus.choices,
        default=CallStatus.PENDING,
    )

    outcome = models.CharField(
        max_length=32,
        choices=CallOutcome.choices,
        blank=True,
        null=True,
    )

    transcript = models.TextField(blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    analysis = models.JSONField(blank=True, null=True)

    started_at = models.DateTimeField(blank=True, null=True)
    ended_at = models.DateTimeField(blank=True, null=True)
    duration_seconds = models.IntegerField(blank=True, null=True)

    metadata = models.JSONField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bdc_calls"
