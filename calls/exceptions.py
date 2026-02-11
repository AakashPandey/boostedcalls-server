"""
Custom exceptions for the calls app.
"""

from rest_framework.exceptions import APIException
from rest_framework import status


class CallNotFoundError(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Call not found."
    default_code = "call_not_found"


class ContactNotFoundError(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Contact not found."
    default_code = "contact_not_found"


class ScriptNotFoundError(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Call script not found."
    default_code = "script_not_found"


class MaxActiveCallsError(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Maximum number of active calls reached."
    default_code = "max_active_calls"


class CallNotCancellableError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Call cannot be cancelled in its current state."
    default_code = "call_not_cancellable"


class VapiAPIError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Failed to communicate with the telephony provider."
    default_code = "vapi_api_error"


class WebhookAuthenticationError(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Invalid or missing webhook secret."
    default_code = "webhook_auth_failed"
