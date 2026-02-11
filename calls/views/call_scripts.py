"""
REST API views for call scripts.

Thin view layer – all business logic lives in ``calls.services.call_scripts``.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from calls.serializers import CallScriptSerializer, CreateCallScriptSerializer, UpdateCallScriptSerializer
from calls.services import call_scripts as script_service


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def script_list_create(request: Request) -> Response:
    """
    GET  /api/scripts/       → list all scripts for the authenticated user
    POST /api/scripts/       → create a new call script
    """
    if request.method == "GET":
        scripts = script_service.list_scripts(request.user)
        return Response(CallScriptSerializer(scripts, many=True).data)

    serializer = CreateCallScriptSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    script = script_service.create_script(
        user=request.user,
        name=data["name"],
        description=data.get("description"),
        custom_prompt=data.get("custom_prompt"),
        first_message=data.get("first_message"),
        call_goals=data.get("call_goals"),
    )
    return Response(CallScriptSerializer(script).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def script_detail(request: Request, script_id: str) -> Response:
    """
    GET    /api/scripts/<id>/  → retrieve a script
    PUT    /api/scripts/<id>/  → full update
    PATCH  /api/scripts/<id>/  → partial update
    DELETE /api/scripts/<id>/  → delete
    """
    if request.method == "GET":
        script = script_service.get_script(script_id, request.user)
        return Response(CallScriptSerializer(script).data)

    if request.method == "DELETE":
        script_service.delete_script(script_id, request.user)
        return Response({"success": True}, status=status.HTTP_200_OK)

    # PUT / PATCH
    partial = request.method == "PATCH"
    serializer = UpdateCallScriptSerializer(data=request.data, partial=partial)
    serializer.is_valid(raise_exception=True)

    script = script_service.update_script(
        script_id,
        request.user,
        **serializer.validated_data,
    )
    return Response(CallScriptSerializer(script).data)
