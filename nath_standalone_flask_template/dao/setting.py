from typing import Optional

from nath_standalone_flask_template.lib.database import DBSession
from nath_standalone_flask_template.models.setting import AppSetting

VALIDATION_REVIEWER_GUEST_LOGIN = 'validation_reviewer_guest_login'


def _truthy(value: str) -> bool:
    return (value or '').strip().lower() in ('1', 'true', 'yes', 'on')


def get_setting(key: str) -> Optional[str]:
    record = AppSetting.query.get(key)
    return record.value if record is not None else None


def set_setting(key: str, value: str) -> AppSetting:
    record = AppSetting.query.get(key)
    if record is None:
        record = AppSetting(key=key, value=value)
        DBSession.add(record)
    else:
        record.value = value
    DBSession.commit()
    return record


def is_validation_reviewer_guest_login_enabled() -> bool:
    return _truthy(get_setting(VALIDATION_REVIEWER_GUEST_LOGIN))


def set_validation_reviewer_guest_login(enabled: bool) -> None:
    set_setting(
        VALIDATION_REVIEWER_GUEST_LOGIN,
        'true' if enabled else 'false',
    )
