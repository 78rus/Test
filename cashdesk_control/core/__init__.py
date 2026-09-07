"""Dependency-free application core."""

from .commands import CommandCatalog, CommandNotFoundError, CommandSpec, Risk, RISK_LABELS
from .db_client import DatabaseClient, DatabaseError, QueryResult, TableInfo
from .events import CoreEvent, EventBus
from .files import EntryInfo, LocalFileSystem, SftpFileSystem
from .logger import configure_logging
from .models import (
    KASS_TYPES,
    CommandResult,
    ConnectionProfile,
    DatabaseSettings,
    JumpHost,
    SessionSnapshot,
    SessionState,
    TunnelDirection,
    TunnelSpec,
    VncSettings,
)
from .paths import AppPaths, app_paths
from .profiles import ProfileNotFoundError, ProfileStore, ProfileStoreError
from .report import KassReport, KassReportBuilder, ReportOptions, ReportSection
from .session import KassSession, SessionConnectionError, SessionTransport
from .session_manager import SessionLimitError, SessionManager, SessionNotFoundError
from .tunnel import SSHTunnel, TunnelBackend, TunnelSnapshot, TunnelState
from .tunnel_manager import TunnelConflictError, TunnelManager, TunnelNotFoundError
from .vnc import VncClient, VncError

__all__ = [
    "AppPaths",
    "CommandCatalog",
    "CommandNotFoundError",
    "CommandResult",
    "CommandSpec",
    "ConnectionProfile",
    "CoreEvent",
    "DatabaseClient",
    "DatabaseError",
    "DatabaseSettings",
    "EntryInfo",
    "EventBus",
    "KASS_TYPES",
    "KassReport",
    "KassReportBuilder",
    "KassSession",
    "LocalFileSystem",
    "ProfileNotFoundError",
    "ProfileStore",
    "ProfileStoreError",
    "QueryResult",
    "RISK_LABELS",
    "ReportOptions",
    "ReportSection",
    "Risk",
    "SftpFileSystem",
    "SessionConnectionError",
    "SessionLimitError",
    "SessionManager",
    "SessionNotFoundError",
    "SessionSnapshot",
    "SessionState",
    "SessionTransport",
    "SSHTunnel",
    "TableInfo",
    "TunnelBackend",
    "TunnelConflictError",
    "TunnelDirection",
    "TunnelManager",
    "TunnelNotFoundError",
    "TunnelSnapshot",
    "TunnelSpec",
    "TunnelState",
    "VncClient",
    "VncError",
    "VncSettings",
    "app_paths",
    "configure_logging",
]
