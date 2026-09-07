"""Core building blocks for the Cashdesk Control application."""

from importlib import metadata as _metadata

try:  # installed (or `pip install -e .`) — read the packaged version
    __version__ = _metadata.version("cashdesk-control")
except _metadata.PackageNotFoundError:  # pragma: no cover - running from a bare checkout
    __version__ = "0.3.0"

from .core.models import ConnectionProfile, JumpHost, SessionSnapshot, SessionState, TunnelSpec
from .core.profiles import ProfileStore
from .core.session import KassSession
from .core.session_manager import SessionManager
from .core.tunnel import SSHTunnel, TunnelState
from .core.tunnel_manager import TunnelManager

__all__ = [
    "ConnectionProfile",
    "JumpHost",
    "KassSession",
    "ProfileStore",
    "SessionManager",
    "SessionSnapshot",
    "SessionState",
    "SSHTunnel",
    "TunnelManager",
    "TunnelSpec",
    "TunnelState",
]
