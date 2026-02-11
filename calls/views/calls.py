"""
REST API views for calls.

Thin view layer – all business logic lives in ``calls.services.calls``.
"""

import hmac
import logging

from django.conf import settings as django_settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from calls.exceptions import WebhookAuthenticationError
from calls.serializers import (
    CallDetailSerializer,
    CallListSerializer,
    CreateCallSerializer,
)
from calls.services import calls as call_service
from calls.services import webhook as webhook_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Calls CRUD
# ---------------------------------------------------------------------------

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def call_list_create(request: Request) -> Response:
    """
    GET  /api/calls/          → paginated list of the user's calls
    POST /api/calls/          → create a new outbound call
    """
    if request.method == "GET":
        page = int(request.query_params.get("page", 1))
        limit = int(request.query_params.get("limit", 20))
        result = call_service.list_calls(request.user, page=page, limit=limit)
        result["data"] = CallListSerializer(result["data"], many=True).data
        return Response(result)

    # POST
    serializer = CreateCallSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    call = call_service.create_call(
        user=request.user,
        contact_id=str(data["contact_id"]),
        assistant_id=data["assistant_id"],
        phone_number_id=data["phone_number_id"],
        script_id=str(data["script_id"]) if data.get("script_id") else None,
        custom_prompt=data.get("custom_prompt"),
        first_message=data.get("first_message"),
        call_goals=data.get("call_goals"),
        metadata=data.get("metadata"),
    )
    return Response(CallDetailSerializer(call).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def call_detail(request: Request, call_id: str) -> Response:
    """GET /api/calls/<call_id>/"""
    call = call_service.get_call(call_id, request.user)
    return Response(CallDetailSerializer(call).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def call_cancel(request: Request, call_id: str) -> Response:
    """POST /api/calls/<call_id>/cancel/"""
    call = call_service.cancel_call(call_id, request.user)
    return Response(CallDetailSerializer(call).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def call_sync(request: Request, call_id: str) -> Response:
    """POST /api/calls/<call_id>/sync/  → re-sync status from Vapi."""
    call = call_service.sync_call_status(call_id, request.user)
    return Response(CallDetailSerializer(call).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def call_pending_count(request: Request) -> Response:
    """GET /api/calls/pending-count/"""
    count = call_service.get_active_call_count(request.user)
    return Response({"count": count})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def call_dashboard_stats(request: Request) -> Response:
    """GET /api/calls/stats/"""
    stats = call_service.get_dashboard_stats(request.user)
    return Response(stats)


# ---------------------------------------------------------------------------
# Vapi webhook
# ---------------------------------------------------------------------------

def _verify_webhook_secret(request: Request) -> None:
    """
    Compare the ``x-vapi-secret`` header against our configured secret.

    Vapi sends the secret you configure on the server-URL / assistant in
    a custom ``x-vapi-secret`` HTTP header with every webhook POST.

    If ``VAPI_WEBHOOK_SECRET`` is not set we skip validation so the
    endpoint stays functional during local development.
    """
    expected = getattr(django_settings, "VAPI_WEBHOOK_SECRET", "")
    if not expected:
        return  # secret not configured – allow all (dev mode)

    received = request.META.get("HTTP_X_VAPI_SECRET", "")
    if not hmac.compare_digest(expected, received):
        logger.warning("Webhook request with invalid secret rejected")
        raise WebhookAuthenticationError()


@api_view(["POST"])
@permission_classes([])  # public – authenticated via x-vapi-secret header
def vapi_webhook(request: Request) -> Response:
    """
    POST /api/calls/webhook/

    Receives events from Vapi.  All payloads follow the shape::

        { "message": { "type": "<event>", "call": { ... }, ... } }

    The webhook service routes each event type to the correct handler.
    """
    _verify_webhook_secret(request)
    result = webhook_service.handle_webhook(request.data)
    return Response(result)
