"""Filesystem access for the two-pane file manager.

Two implementations share one interface: the workstation's local disk and the
cashier over SFTP. The manager widget never learns which one it is holding.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import shutil
import stat as stat_module
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, Sequence

HIDDEN_SUFFIXES = (".tmp", ".part")


@dataclass(frozen=True, slots=True)
class EntryInfo:
    name: str
    path: str
    is_dir: bool
    is_link: bool
    size: int
    modified: datetime | None
    permissions: str = ""
    owner: str = ""

    @property
    def display_size(self) -> str:
        if self.is_dir:
            return "—"
        return human_size(self.size)

    @property
    def display_modified(self) -> str:
        return self.modified.strftime("%Y-%m-%d %H:%M") if self.modified else "—"


def human_size(value: float) -> str:
    size = float(value)
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024 or unit == "T":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}T"


def mode_to_string(mode: int) -> str:
    kind = "d" if stat_module.S_ISDIR(mode) else ("l" if stat_module.S_ISLNK(mode) else "-")
    bits = "".join(
        char if mode & flag else "-"
        for char, flag in (
            ("r", stat_module.S_IRUSR),
            ("w", stat_module.S_IWUSR),
            ("x", stat_module.S_IXUSR),
            ("r", stat_module.S_IRGRP),
            ("w", stat_module.S_IWGRP),
            ("x", stat_module.S_IXGRP),
            ("r", stat_module.S_IROTH),
            ("w", stat_module.S_IWOTH),
            ("x", stat_module.S_IXOTH),
        )
    )
    return kind + bits


class FileSystem(Protocol):
    """The operations the file manager needs from any backend."""

    kind: str

    async def listdir(self, path: str) -> list[EntryInfo]:
        ...

    async def read_bytes(self, path: str, limit: int | None = None) -> bytes:
        ...

    async def write_bytes(self, path: str, data: bytes) -> None:
        ...

    async def remove(self, path: str, *, recursive: bool = False) -> None:
        ...

    async def rename(self, source: str, target: str) -> None:
        ...

    async def mkdir(self, path: str) -> None:
        ...

    async def download(self, remote: str, local: str) -> None:
        ...

    async def upload(self, local: str, remote: str) -> None:
        ...


class LocalFileSystem:
    """The workstation's own disk."""

    kind = "local"

    def __init__(self, root: str | None = None) -> None:
        self.root = str(Path(root).expanduser()) if root else (
            "C:\\" if os.name == "nt" else "/"
        )

    def _resolve(self, path: str) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = Path(self.root) / candidate
        return candidate

    async def listdir(self, path: str) -> list[EntryInfo]:
        return await asyncio.to_thread(self._listdir_sync, path)

    def _listdir_sync(self, path: str) -> list[EntryInfo]:
        target = self._resolve(path)
        entries: list[EntryInfo] = []
        for item in target.iterdir():
            try:
                info = item.lstat()
                entries.append(
                    EntryInfo(
                        name=item.name,
                        path=str(item),
                        is_dir=stat_module.S_ISDIR(info.st_mode),
                        is_link=stat_module.S_ISLNK(info.st_mode),
                        size=info.st_size,
                        modified=datetime.fromtimestamp(info.st_mtime),
                        permissions=mode_to_string(info.st_mode),
                        owner=str(info.st_uid),
                    )
                )
            except OSError:
                continue
        entries.sort(key=lambda entry: (not entry.is_dir, entry.name.lower()))
        return entries

    async def read_bytes(self, path: str, limit: int | None = None) -> bytes:
        return await asyncio.to_thread(self._read_sync, path, limit)

    def _read_sync(self, path: str, limit: int | None) -> bytes:
        with open(self._resolve(path), "rb") as handle:
            return handle.read(limit) if limit else handle.read()

    async def write_bytes(self, path: str, data: bytes) -> None:
        await asyncio.to_thread(self._write_sync, path, data)

    def _write_sync(self, path: str, data: bytes) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(data)

    async def remove(self, path: str, *, recursive: bool = False) -> None:
        await asyncio.to_thread(self._remove_sync, path, recursive)

    def _remove_sync(self, path: str, recursive: bool) -> None:
        target = self._resolve(path)
        if target.is_dir() and not target.is_symlink():
            if not recursive:
                raise IsADirectoryError(f"{target} — каталог")
            shutil.rmtree(target)
        else:
            target.unlink()

    async def rename(self, source: str, target: str) -> None:
        await asyncio.to_thread(self._resolve(source).rename, self._resolve(target))

    async def mkdir(self, path: str) -> None:
        await asyncio.to_thread(lambda: self._resolve(path).mkdir(parents=True, exist_ok=True))

    async def download(self, remote: str, local: str) -> None:
        await asyncio.to_thread(shutil.copyfile, self._resolve(remote), self._resolve(local))

    async def upload(self, local: str, remote: str) -> None:
        await asyncio.to_thread(shutil.copyfile, self._resolve(local), self._resolve(remote))


class SftpFileSystem:
    """The cashier's disk, reached through the session's SFTP client.

    Written against AsyncSSH's ``SFTPClient``, whose methods are coroutines. A
    synchronous client (paramiko, or a test double) also works: every call goes
    through :func:`_call`, which awaits only when it has to.
    """

    kind = "sftp"

    def __init__(self, sftp: Any, home: str = "/home/tc") -> None:
        self._sftp = sftp
        self.home = home

    def _resolve(self, path: str) -> str:
        if not path or path == "~":
            return self.home
        if path.startswith("~"):
            return str(PurePosixPath(self.home) / path[1:].lstrip("/"))
        return path

    async def listdir(self, path: str) -> list[EntryInfo]:
        target = self._resolve(path)
        entries = await _call(self._sftp.listdir, target)
        result: list[EntryInfo] = []
        for name in entries:
            remote = f"{target.rstrip('/')}/{name}"
            try:
                attributes = await _call(self._sftp.stat, remote)
            except OSError:
                try:
                    attributes = await _call(self._sftp.lstat, remote)
                except OSError:
                    continue
            mode = getattr(attributes, "permissions", 0) or 0
            modified = getattr(attributes, "mtime", None)
            result.append(
                EntryInfo(
                    name=name,
                    path=remote,
                    is_dir=stat_module.S_ISDIR(mode),
                    is_link=stat_module.S_ISLNK(mode),
                    size=getattr(attributes, "size", 0) or 0,
                    modified=datetime.fromtimestamp(modified) if modified else None,
                    permissions=mode_to_string(mode) if mode else "",
                    owner=str(getattr(attributes, "uid", "") or ""),
                )
            )
        result.sort(key=lambda entry: (not entry.is_dir, entry.name.lower()))
        return result

    async def read_bytes(self, path: str, limit: int | None = None) -> bytes:
        handle = await _call(self._sftp.open, self._resolve(path), "rb")
        try:
            return await _call(handle.read, limit) if limit else await _read_all(handle)
        finally:
            await _call(handle.close)

    async def write_bytes(self, path: str, data: bytes) -> None:
        handle = await _call(self._sftp.open, self._resolve(path), "wb")
        try:
            await _call(handle.write, data)
        finally:
            await _call(handle.close)

    async def remove(self, path: str, *, recursive: bool = False) -> None:
        target = self._resolve(path)
        if recursive:
            await _call(self._sftp.rmtree, target)
            return
        try:
            await _call(self._sftp.remove, target)
        except OSError:
            await _call(self._sftp.rmdir, target)

    async def rename(self, source: str, target: str) -> None:
        await _call(self._sftp.rename, self._resolve(source), self._resolve(target))

    async def mkdir(self, path: str) -> None:
        await _call(self._sftp.makedirs, self._resolve(path), exist_ok=True)

    async def download(self, remote: str, local: str) -> None:
        await _call(self._sftp.get, self._resolve(remote), local)

    async def upload(self, local: str, remote: str) -> None:
        await _call(self._sftp.put, local, self._resolve(remote))


async def _call(method: Any, *args: Any, **kwargs: Any) -> Any:
    """Call *method*, awaiting it only when it returns an awaitable."""

    result = method(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


async def _read_all(handle: Any) -> bytes:
    if hasattr(handle, "readall"):
        return await _call(handle.readall)
    chunks: list[bytes] = []
    while True:
        chunk = await _call(handle.read, 65536)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def parent_of(path: str, kind: str = "posix") -> str:
    if kind == "local" and os.name == "nt":
        parent = str(Path(path).parent)
        return parent if parent != path else path
    resolved = PurePosixPath(path)
    parent = str(resolved.parent)
    return parent if parent != path else "/"


def join(path: str, name: str, kind: str = "posix") -> str:
    if kind == "local" and os.name == "nt":
        return str(Path(path) / name)
    return str(PurePosixPath(path) / name)


def is_text_file(name: str) -> bool:
    lowered = name.lower()
    if lowered.endswith(HIDDEN_SUFFIXES):
        return False
    text_suffixes = {
        ".txt", ".log", ".conf", ".cfg", ".ini", ".json", ".xml", ".yaml", ".yml",
        ".sh", ".py", ".sql", ".properties", ".csv", ".md", ".service", ".rules",
    }
    suffix = PurePosixPath(lowered).suffix
    return suffix in text_suffixes or suffix == ""


__all__ = [
    "EntryInfo",
    "FileSystem",
    "LocalFileSystem",
    "SftpFileSystem",
    "human_size",
    "is_text_file",
    "join",
    "mode_to_string",
    "parent_of",
]
