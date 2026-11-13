"""Token-authenticated HTTP API."""

from flask import Blueprint, g, jsonify, request

from nath_standalone_flask_template.lib.api_auth import ApiTokenAuthenticator

rest = Blueprint('rest', __name__)


@rest.before_request
def authenticate_api_token():
    return ApiTokenAuthenticator().require(request)


@rest.route('/test', methods=['GET'])
def get_test():
    """Simple authenticated probe: who the token belongs to."""
    user = g.api_user
    return jsonify({
        'ok': True,
        'user': user.ide,
        'user_id': user.id,
    })
