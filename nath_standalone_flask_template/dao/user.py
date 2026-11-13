from datetime import datetime
from typing import List, Optional

from flask_babel import gettext as _

from nath_standalone_flask_template import models
from nath_standalone_flask_template.lib.api_token import ApiToken
from nath_standalone_flask_template.lib.database import DBSession
from nath_standalone_flask_template.lib.exc import DomainError


def get_active_users() -> List[models.User]:
    return models.User.query.filter_by(active=True).order_by(models.User.last_name).all()


def get_user(pk: int) -> Optional[models.User]:
    return models.User.query.get(pk)


def get_user_by_api_token(raw_token: str) -> Optional[models.User]:
    token = ApiToken(raw_token)
    if not token.is_valid_format():
        return None
    user = models.User.query.filter_by(api_token_hash=token.digest()).first()
    if user is None or not user.can_use_api_token():
        return None
    return user


def generate_api_token(user_id: int) -> dict:
    user = get_user(user_id)
    if user is None:
        raise DomainError(_("User not found."))
    token = ApiToken.generate()
    user.api_token_hash = token.digest()
    user.api_token_prefix = token.display_prefix()
    user.api_token_created_at = datetime.utcnow()
    DBSession.commit()
    return {
        "token": token.raw,
        "prefix": user.api_token_prefix,
        "created_at": user.api_token_created_at,
        "user": user,
    }


def revoke_api_token(user_id: int) -> models.User:
    user = get_user(user_id)
    if user is None:
        raise DomainError(_("User not found."))
    if not user.has_api_token():
        raise DomainError(_("This user has no API token."))
    user.api_token_hash = None
    user.api_token_prefix = None
    user.api_token_created_at = None
    DBSession.commit()
    return user
