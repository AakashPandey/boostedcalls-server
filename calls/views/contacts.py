"""
REST API views for contacts.

Thin view layer – all business logic lives in ``calls.services.contacts``.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from calls.serializers import ContactSerializer, CreateContactSerializer, UpdateContactSerializer
from calls.services import contacts as contact_service


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def contact_list_create(request: Request) -> Response:
    """
    GET  /api/contacts/      → list all contacts for the authenticated user
    POST /api/contacts/      → create a new contact
    """
    if request.method == "GET":
        contacts = contact_service.list_contacts(request.user)
        return Response(ContactSerializer(contacts, many=True).data)

    serializer = CreateContactSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    contact = contact_service.create_contact(
        user=request.user,
        name=data["name"],
        phone=data["phone"],
        email=data.get("email"),
        metadata=data.get("metadata"),
    )
    return Response(ContactSerializer(contact).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def contact_detail(request: Request, contact_id: str) -> Response:
    """
    GET    /api/contacts/<id>/  → retrieve a contact
    PUT    /api/contacts/<id>/  → full update
    PATCH  /api/contacts/<id>/  → partial update
    DELETE /api/contacts/<id>/  → delete
    """
    if request.method == "GET":
        contact = contact_service.get_contact(contact_id, request.user)
        return Response(ContactSerializer(contact).data)

    if request.method == "DELETE":
        contact_service.delete_contact(contact_id, request.user)
        return Response({"message": "Contact deleted successfully."}, status=status.HTTP_200_OK)

    # PUT / PATCH
    partial = request.method == "PATCH"
    serializer = UpdateContactSerializer(data=request.data, partial=partial)
    serializer.is_valid(raise_exception=True)

    contact = contact_service.update_contact(
        contact_id,
        request.user,
        **serializer.validated_data,
    )
    return Response(ContactSerializer(contact).data)
