import logging

from flask import request, session
from flask_login import current_user, login_user

from nath_standalone_flask_template.lib import config
from nath_standalone_flask_template.lib.const import CONTEXT_VALIDATION
from nath_standalone_flask_template import dao
from nath_standalone_flask_template.models.user import User

log = logging.getLogger(__name__)

SESSION_DECLINED_KEY = 'validation_reviewer_declined'


class ValidationGuestReviewer:
    """Optional passwordless reviewer sessions on the validation deployment."""

    @classmethod
    def active(cls) -> bool:
        return (
            config.CONTEXT == CONTEXT_VALIDATION
            and dao.is_validation_reviewer_guest_login_enabled()
        )

    @classmethod
    def mark_declined(cls) -> None:
        session[SESSION_DECLINED_KEY] = True

    @classmethod
    def clear_declined(cls) -> None:
        session.pop(SESSION_DECLINED_KEY, None)

    @classmethod
    def user_declined(cls) -> bool:
        return bool(session.get(SESSION_DECLINED_KEY))

    @classmethod
    def _reviewer_user(cls):
        username = config.REVIEWER_USER_USERNAME
        if not username:
            return None
        user = User.query.filter_by(ide=username).first()
        if user is None or not user.is_active():
            return None
        return user

    @classmethod
    def login_reviewer(cls):
        user = cls._reviewer_user()
        if user is None:
            return None
        cls.clear_declined()
        login_user(user, remember=True)
        log.info("Validation guest login as reviewer '%s'", user.ide)
        return user

    @classmethod
    def maybe_auto_login(cls) -> None:
        if not cls.active():
            return
        if current_user.is_authenticated:
            return
        if cls.user_declined():
            return
        if request.blueprint == 'rest' or (request.path or '').startswith('/rest'):
            return
        cls.login_reviewer()
