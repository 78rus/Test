"""Dependency-free application core."""

from .events import CoreEvent, EventBus
from .logger import configure_logging
from .paths import AppPaths, app_paths
from .models import ConnectionProfile, JumpHost, SessionSnapshot, SessionState, TunnelDirection, TunnelSpec
from .session import KassSession, SessionConnectionError, SessionTransport
from .session_manager import SessionLimitError, SessionManager, SessionNotFoundError
from .tunnel import SSHTunnel, TunnelBackend, TunnelSnapshot, TunnelState
from .tunnel_manager import TunnelConflictError, TunnelManager, TunnelNotFoundError

__all__ = [
    "AppPaths",
    "ConnectionProfile",
    "CoreEvent",
    "EventBus",
    "app_paths",
    "configure_logging",
    "JumpHost",
    "ProfileNotFoundError",
    "ProfileStore",
    "ProfileStoreError",
    "KassSession",
    "SessionConnectionError",
    "SessionLimitError",
    "SessionManager",
    "SessionNotFoundError",
    "SessionSnapshot",
    "SessionState",
    "SessionTransport",
    "SSHTunnel",
    "TunnelDirection",
    "TunnelBackend",
    "TunnelConflictError",
    "TunnelManager",
    "TunnelNotFoundError",
    "TunnelSnapshot",
    "TunnelSpec",
    "TunnelState",
]
