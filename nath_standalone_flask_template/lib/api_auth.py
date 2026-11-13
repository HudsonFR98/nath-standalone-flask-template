from functools import wraps

from flask import g, jsonify, request
from flask_babel import gettext as _

from nath_standalone_flask_template import dao
from nath_standalone_flask_template.lib.const import API_TOKEN_HEADER


class ApiTokenAuthenticator:
    """Resolve the calling user from a Bearer or X-API-Token header."""

    def extract_token(self, http_request) -> str:
        authorization = http_request.headers.get("Authorization", "")
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
        header_token = http_request.headers.get(API_TOKEN_HEADER, "").strip()
        return header_token

    def authenticate(self, http_request):
        raw = self.extract_token(http_request)
        if not raw:
            return None
        return dao.get_user_by_api_token(raw)

    def require(self, http_request):
        user = self.authenticate(http_request)
        if user is None:
            return jsonify({"error": _("Invalid or missing API token")}), 401
        g.api_user = user
        return None


def token_required(view):
    """Protect a REST view. Prefer the rest blueprint before_request for all routes."""

    @wraps(view)
    def decorated(*args, **kwargs):
        failure = ApiTokenAuthenticator().require(request)
        if failure is not None:
            return failure
        return view(*args, **kwargs)

    return decorated
