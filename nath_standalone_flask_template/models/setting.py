from sqlalchemy import Column, String

from nath_standalone_flask_template.lib.database import Base, DBSession


class AppSetting(Base):
    """Key/value application settings (admin-togglable flags)."""
    __tablename__ = 'app_settings'

    key = Column(String(64), primary_key=True)
    value = Column(String(255), nullable=False)

    def __init__(self, key, value):
        self.key = key
        self.value = value


AppSetting.query = DBSession.query_property()
