import hashlib
import secrets

from nath_standalone_flask_template.lib.const import (
    API_TOKEN_BYTES,
    API_TOKEN_DISPLAY_LENGTH,
    API_TOKEN_PREFIX,
)


class ApiToken:
    """Opaque user API token. Persist only the SHA-256 digest."""

    def __init__(self, raw: str):
        self.raw = (raw or "").strip()

    @classmethod
    def generate(cls) -> "ApiToken":
        return cls(f"{API_TOKEN_PREFIX}{secrets.token_urlsafe(API_TOKEN_BYTES)}")

    def digest(self) -> str:
        return hashlib.sha256(self.raw.encode("utf-8")).hexdigest()

    def display_prefix(self) -> str:
        return self.raw[:API_TOKEN_DISPLAY_LENGTH]

    def is_valid_format(self) -> bool:
        return bool(self.raw) and self.raw.startswith(API_TOKEN_PREFIX)
