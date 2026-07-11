from typing import Protocol


SERVICE_NAME = "guarded-harness"
ACCOUNT_NAME = "api-key"


class KeyringBackend(Protocol):
    def get_password(self, service_name: str, username: str) -> str | None: ...

    def set_password(self, service_name: str, username: str, password: str) -> None: ...

    def delete_password(self, service_name: str, username: str) -> None: ...


class InMemoryKeyring:
    """A test-only keyring backend that never writes credentials to disk."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], str] = {}

    def get_password(self, service_name: str, username: str) -> str | None:
        return self._values.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self._values[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
        self._values.pop((service_name, username), None)


class CredentialStore:
    def __init__(self, keyring_backend: KeyringBackend | None = None) -> None:
        self._keyring = keyring_backend if keyring_backend is not None else self._load_keyring()

    @staticmethod
    def _load_keyring() -> KeyringBackend | None:
        try:
            import keyring
        except ImportError:
            return None
        return keyring

    def set_key(self, key: str) -> None:
        if not key:
            raise ValueError("credential must not be empty")
        backend = self._require_backend()
        backend.set_password(SERVICE_NAME, ACCOUNT_NAME, key)

    def get_key(self) -> str | None:
        if self._keyring is None:
            return None
        try:
            return self._keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
        except Exception:
            return None

    def status(self) -> bool:
        return self.get_key() is not None

    def clear_key(self) -> None:
        backend = self._require_backend()
        backend.delete_password(SERVICE_NAME, ACCOUNT_NAME)

    def _require_backend(self) -> KeyringBackend:
        if self._keyring is None:
            raise RuntimeError("OS keyring is unavailable; cannot store credentials")
        return self._keyring
