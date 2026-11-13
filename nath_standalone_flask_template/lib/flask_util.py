import logging

from functools import wraps
from flask import abort, g
from flask_login import login_required as flask_login_required, current_user

from nath_standalone_flask_template.lib.database import DBSession

log = logging.getLogger(__name__)


# Use Flask-Login's login_required decorator
login_required = flask_login_required


def before_request():
    """ launched before each request """
    from nath_standalone_flask_template.lib.validation_guest import ValidationGuestReviewer

    ValidationGuestReviewer.maybe_auto_login()

    g.user = current_user
    if current_user.is_authenticated:
        current_user.reload_permissions()


def after_request():
    """ launched after each request """

    DBSession.remove()


def require_user(predicate):
    """Require a logged-in user who satisfies predicate(user)."""

    def decorator(view):
        @wraps(view)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_required(view)(*args, **kwargs)
            if not predicate(current_user):
                abort(403)
            return view(*args, **kwargs)

        return decorated_function

    return decorator


admin_required = require_user(lambda user: user.has_permission("admin"))
staff_required = require_user(lambda user: user.has_role("admin", "reviewer"))
admin_role_required = require_user(lambda user: user.has_role("admin"))
