"""Value objects shared by sessions, tunnels, reports and UI adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4


class SessionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    ERROR = "error"
    CLOSING = "closing"


class TunnelDirection(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"


#: Cashier flavours understood by the detector and shown in the session panel.
KASS_TYPES: tuple[str, ...] = ("POS", "SCO", "Touch", "Hybrid", "Не определена")


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Outcome of one remote (or local) shell command."""

    command: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        """``True`` when the command ran and returned a zero exit status."""

        return self.error is None and self.exit_code == 0

    @property
    def output(self) -> str:
        """Stdout plus stderr, with empty parts removed."""

        parts = [self.stdout.rstrip(), self.stderr.rstrip()]
        return "\n".join(part for part in parts if part)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class JumpHost:
    """An SSH hop used to reach a cashier that is not directly accessible."""

    host: str
    username: str
    port: int = 22
    credential_ref: str | None = None

    def __post_init__(self) -> None:
        _validate_host(self.host)
        _validate_username(self.username)
        _validate_port(self.port)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "JumpHost":
        return cls(
            host=str(data["host"]),
            username=str(data["username"]),
            port=int(data.get("port", 22)),
            credential_ref=data.get("credential_ref"),
        )


@dataclass(frozen=True, slots=True)
class TunnelSpec:
    """A single local or remote SSH port forward."""

    name: str
    local_port: int
    target_host: str
    target_port: int
    direction: TunnelDirection = TunnelDirection.LOCAL
    local_host: str = "127.0.0.1"
    remote_host: str = "0.0.0.0"
    remote_port: int | None = None
    auto_restart: bool = True
    reconnect_delay: float = 5.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tunnel name must not be empty")
        _validate_host(self.target_host)
        _validate_host(self.local_host)
        _validate_host(self.remote_host)
        # 0 on the local side means "let the OS pick a free port", which is the
        # default for VNC and database forwards.
        _validate_bind_port(self.local_port)
        _validate_port(self.target_port)
        if self.remote_port is not None:
            _validate_port(self.remote_port)
        if self.reconnect_delay < 0:
            raise ValueError("reconnect_delay must be non-negative")
        object.__setattr__(self, "direction", TunnelDirection(self.direction))

    @property
    def tunnel_id(self) -> str:
        return self.name

    @property
    def bind_port(self) -> int:
        return self.remote_port if self.direction is TunnelDirection.REMOTE and self.remote_port else self.local_port

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["direction"] = self.direction.value
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TunnelSpec":
        return cls(
            name=str(data["name"]),
            local_port=int(data["local_port"]),
            target_host=str(data["target_host"]),
            target_port=int(data["target_port"]),
            direction=TunnelDirection(data.get("direction", TunnelDirection.LOCAL.value)),
            local_host=str(data.get("local_host", "127.0.0.1")),
            remote_host=str(data.get("remote_host", "0.0.0.0")),
            remote_port=int(data["remote_port"]) if data.get("remote_port") is not None else None,
            auto_restart=bool(data.get("auto_restart", True)),
            reconnect_delay=float(data.get("reconnect_delay", 5.0)),
        )


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Connection data for the cashier database (reached through a tunnel)."""

    dialect: str = "postgresql"
    host: str = "127.0.0.1"
    port: int = 5432
    database: str = "cash"
    username: str = "postgres"
    credential_ref: str | None = None
    schema: str = "public"
    #: ``True`` when the port must be forwarded through the SSH session first.
    via_tunnel: bool = True
    local_port: int | None = None

    def __post_init__(self) -> None:
        _validate_port(self.port)
        if self.local_port is not None:
            _validate_port(self.local_port)

    @property
    def tunnel_spec(self) -> TunnelSpec | None:
        """Local forward that makes the database reachable, if one is needed."""

        if not self.via_tunnel or self.local_port is None:
            return None
        return TunnelSpec(
            name=f"db-{self.local_port}",
            local_port=self.local_port,
            target_host=self.host,
            target_port=self.port,
        )

    def url(self, password: str | None = None, host: str | None = None, port: int | None = None) -> str:
        """SQLAlchemy URL for the database.

        ``host``/``port`` override the stored values so a caller can point at the
        locally forwarded endpoint without mutating the profile. SQLite takes a
        file path instead of a network endpoint, so it is handled separately.
        """

        from urllib.parse import quote_plus

        if self.dialect == "sqlite":
            return f"sqlite:///{self.database}"
        user = quote_plus(self.username)
        secret = f":{quote_plus(password)}" if password else ""
        target_host = host or self.host
        target_port = port or self.port
        return f"{self.dialect}://{user}{secret}@{target_host}:{target_port}/{quote_plus(self.database)}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DatabaseSettings":
        if not data:
            return cls()
        return cls(
            dialect=str(data.get("dialect", "postgresql")),
            host=str(data.get("host", "127.0.0.1")),
            port=int(data.get("port", 5432)),
            database=str(data.get("database", "cash")),
            username=str(data.get("username", "postgres")),
            credential_ref=data.get("credential_ref"),
            schema=str(data.get("schema", "public")),
            via_tunnel=bool(data.get("via_tunnel", True)),
            local_port=int(data["local_port"]) if data.get("local_port") else None,
        )


@dataclass(frozen=True, slots=True)
class VncSettings:
    """Remote desktop endpoint of a cashier."""

    host: str = "127.0.0.1"
    port: int = 5900
    credential_ref: str | None = None
    shared: bool = True
    local_port: int | None = None
    via_tunnel: bool = True

    def __post_init__(self) -> None:
        _validate_port(self.port)
        if self.local_port is not None:
            _validate_port(self.local_port)

    @property
    def tunnel_spec(self) -> TunnelSpec | None:
        if not self.via_tunnel or self.local_port is None:
            return None
        return TunnelSpec(
            name=f"vnc-{self.local_port}",
            local_port=self.local_port,
            target_host=self.host,
            target_port=self.port,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VncSettings":
        if not data:
            return cls()
        return cls(
            host=str(data.get("host", "127.0.0.1")),
            port=int(data.get("port", 5900)),
            credential_ref=data.get("credential_ref"),
            shared=bool(data.get("shared", True)),
            local_port=int(data["local_port"]) if data.get("local_port") else None,
            via_tunnel=bool(data.get("via_tunnel", True)),
        )


@dataclass(frozen=True, slots=True)
class ConnectionProfile:
    """Serializable connection settings with no password fields by design."""

    name: str
    host: str
    username: str
    port: int = 22
    profile_id: str = field(default_factory=lambda: uuid4().hex)
    credential_ref: str | None = None
    private_key: str | None = None
    known_hosts: str | None = None
    jump_hosts: tuple[JumpHost, ...] = ()
    tunnels: tuple[TunnelSpec, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)
    # Cashier identity -----------------------------------------------------
    kass_type: str = "Не определена"
    location: str = ""
    color: str = "blue"
    # Service endpoints ----------------------------------------------------
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    vnc: VncSettings = field(default_factory=VncSettings)
    sudo_credential_ref: str | None = None
    shell: str = "/bin/bash"
    #: Extra ``PATH`` entries on the cashier (``cash`` usually lives in ~/bin).
    remote_path: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("profile name must not be empty")
        _validate_host(self.host)
        _validate_username(self.username)
        _validate_port(self.port)
        if not self.profile_id.strip():
            raise ValueError("profile_id must not be empty")
        object.__setattr__(self, "jump_hosts", tuple(self.jump_hosts))
        object.__setattr__(self, "tunnels", tuple(self.tunnels))
        object.__setattr__(self, "metadata", dict(self.metadata))
        if self.private_key:
            object.__setattr__(self, "private_key", str(Path(self.private_key).expanduser()))

    def replaced(self, **changes: Any) -> "ConnectionProfile":
        """Return a copy of the profile with *changes* applied."""

        data = self.to_dict()
        data.update(changes)
        return ConnectionProfile.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation safe to persist."""

        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "host": self.host,
            "username": self.username,
            "port": self.port,
            "credential_ref": self.credential_ref,
            "private_key": self.private_key,
            "known_hosts": self.known_hosts,
            "jump_hosts": [host.to_dict() for host in self.jump_hosts],
            "tunnels": [tunnel.to_dict() for tunnel in self.tunnels],
            "metadata": dict(self.metadata),
            "kass_type": self.kass_type,
            "location": self.location,
            "color": self.color,
            "database": self.database.to_dict(),
            "vnc": self.vnc.to_dict(),
            "sudo_credential_ref": self.sudo_credential_ref,
            "shell": self.shell,
            "remote_path": self.remote_path,
        }

    def redacted(self) -> dict[str, Any]:
        """Return a log-friendly profile without secret material."""

        data = self.to_dict()
        if data.get("private_key"):
            data["private_key"] = "<configured>"
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ConnectionProfile":
        return cls(
            profile_id=str(data.get("profile_id") or uuid4().hex),
            name=str(data["name"]),
            host=str(data["host"]),
            username=str(data.get("username") or "tc"),
            port=int(data.get("port", 22)),
            credential_ref=data.get("credential_ref"),
            private_key=data.get("private_key"),
            known_hosts=data.get("known_hosts"),
            jump_hosts=tuple(JumpHost.from_dict(item) for item in data.get("jump_hosts", ())),
            tunnels=tuple(TunnelSpec.from_dict(item) for item in data.get("tunnels", ())),
            metadata={str(key): str(value) for key, value in data.get("metadata", {}).items()},
            kass_type=str(data.get("kass_type") or "Не определена"),
            location=str(data.get("location") or ""),
            color=str(data.get("color") or "blue"),
            database=DatabaseSettings.from_dict(data.get("database") or {}),
            vnc=VncSettings.from_dict(data.get("vnc") or {}),
            sudo_credential_ref=data.get("sudo_credential_ref"),
            shell=str(data.get("shell") or "/bin/bash"),
            remote_path=str(data.get("remote_path") or ""),
        )


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    session_id: str
    name: str
    host: str
    state: SessionState
    connected_at: str | None
    last_error: str | None
    tunnel_ids: tuple[str, ...]
    kass_type: str = "Не определена"
    location: str = ""
    color: str = "blue"
    version: str = ""
    uptime: str = ""
    facts: Mapping[str, str] = field(default_factory=dict)

    def fact(self, key: str, default: str = "—") -> str:
        return self.facts.get(key) or default


def _validate_host(value: str) -> None:
    if not value or not value.strip() or any(char.isspace() for char in value):
        raise ValueError("host must be a non-empty value without spaces")


def _validate_username(value: str) -> None:
    if not value or not value.strip() or any(char.isspace() for char in value):
        raise ValueError("username must be a non-empty value without spaces")


def _validate_port(value: int) -> None:
    if not isinstance(value, int) or not 1 <= value <= 65535:
        raise ValueError("port must be between 1 and 65535")


def _validate_bind_port(value: int) -> None:
    """A local bind port may be 0, meaning the OS chooses a free one."""

    if not isinstance(value, int) or not 0 <= value <= 65535:
        raise ValueError("bind port must be between 0 and 65535")
