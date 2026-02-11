"""
DRF serializers for the calls app.
"""

from rest_framework import serializers

from calls.models import Call, CallScript, Contact


# ---------------------------------------------------------------------------
# Contact
# ---------------------------------------------------------------------------

class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# ---------------------------------------------------------------------------
# CallScript
# ---------------------------------------------------------------------------

class CallScriptSerializer(serializers.ModelSerializer):
    class Meta:
        model = CallScript
        fields = [
            "id",
            "name",
            "description",
            "custom_prompt",
            "first_message",
            "call_goals",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CallScriptSummarySerializer(serializers.ModelSerializer):
    """Lightweight representation embedded in call detail responses."""

    class Meta:
        model = CallScript
        fields = ["id", "name", "custom_prompt", "first_message", "call_goals"]


# ---------------------------------------------------------------------------
# Contact – creation / update input
# ---------------------------------------------------------------------------

class CreateContactSerializer(serializers.Serializer):
    name = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    metadata = serializers.JSONField(required=False, allow_null=True)


class UpdateContactSerializer(serializers.Serializer):
    name = serializers.CharField(required=False)
    phone = serializers.CharField(required=False)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    metadata = serializers.JSONField(required=False, allow_null=True)


# ---------------------------------------------------------------------------
# CallScript – creation / update input
# ---------------------------------------------------------------------------

class CreateCallScriptSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    custom_prompt = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    first_message = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    call_goals = serializers.JSONField(required=False, allow_null=True)


class UpdateCallScriptSerializer(serializers.Serializer):
    name = serializers.CharField(required=False)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    custom_prompt = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    first_message = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    call_goals = serializers.JSONField(required=False, allow_null=True)


# ---------------------------------------------------------------------------
# Call – creation input
# ---------------------------------------------------------------------------

class CallGoalSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField()
    successCriteria = serializers.CharField(required=False, allow_blank=True)


class CreateCallSerializer(serializers.Serializer):
    contact_id = serializers.UUIDField()
    assistant_id = serializers.CharField()
    phone_number_id = serializers.CharField()
    script_id = serializers.UUIDField(required=False, allow_null=True)
    custom_prompt = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    first_message = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    call_goals = CallGoalSerializer(many=True, required=False, allow_null=True)
    metadata = serializers.JSONField(required=False, allow_null=True)


# ---------------------------------------------------------------------------
# Call – list / detail output
# ---------------------------------------------------------------------------

class CallListSerializer(serializers.ModelSerializer):
    """Compact representation for the paginated list endpoint."""

    contact_name = serializers.CharField(source="contact.name", read_only=True)
    contact_phone = serializers.CharField(source="contact.phone", read_only=True)

    class Meta:
        model = Call
        fields = [
            "id",
            "contact_id",
            "contact_name",
            "contact_phone",
            "status",
            "outcome",
            "started_at",
            "ended_at",
            "created_at",
        ]


class CallDetailSerializer(serializers.ModelSerializer):
    """Full representation for the single-call detail endpoint."""

    contact = ContactSerializer(read_only=True)
    script = CallScriptSummarySerializer(read_only=True)

    class Meta:
        model = Call
        fields = [
            "id",
            "contact",
            "script",
            "vapi_call_id",
            "assistant_id",
            "phone_number_id",
            "status",
            "outcome",
            "transcript",
            "summary",
            "analysis",
            "started_at",
            "ended_at",
            "duration_seconds",
            "metadata",
            "error_message",
            "created_at",
            "updated_at",
        ]


