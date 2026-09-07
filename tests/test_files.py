"""Filesystem helpers: the local pane and the SFTP abstraction."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from cashdesk_control.core.files import (
    EntryInfo,
    LocalFileSystem,
    SftpFileSystem,
    human_size,
    is_text_file,
    join,
    mode_to_string,
    parent_of,
)


class LocalFileSystemTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        (self.root / "sub").mkdir()
        (self.root / "sub" / "cash.conf").write_text("key=value\n", encoding="utf-8")
        (self.root / "notes.txt").write_text("hello", encoding="utf-8")
        self.fs = LocalFileSystem(str(self.root))

    async def asyncTearDown(self) -> None:
        self._temp.cleanup()

    async def test_listdir_sorts_directories_first(self) -> None:
        entries = await self.fs.listdir(str(self.root))
        self.assertEqual([entry.name for entry in entries], ["sub", "notes.txt"])
        self.assertTrue(entries[0].is_dir)
        self.assertFalse(entries[0].permissions == "")

    async def test_read_and_write(self) -> None:
        path = str(self.root / "notes.txt")
        self.assertEqual(await self.fs.read_bytes(path), b"hello")
        await self.fs.write_bytes(path, b"changed")
        self.assertEqual(await self.fs.read_bytes(path), b"changed")

    async def test_read_with_limit(self) -> None:
        self.assertEqual(await self.fs.read_bytes(str(self.root / "notes.txt"), 3), b"hel")

    async def test_write_creates_parent_directories(self) -> None:
        target = str(self.root / "deep" / "nested" / "file.txt")
        await self.fs.write_bytes(target, b"x")
        self.assertTrue(Path(target).exists())

    async def test_mkdir_rename_remove(self) -> None:
        created = str(self.root / "newdir")
        await self.fs.mkdir(created)
        self.assertTrue(Path(created).is_dir())
        renamed = str(self.root / "renamed")
        await self.fs.rename(created, renamed)
        self.assertTrue(Path(renamed).is_dir())
        await self.fs.remove(renamed, recursive=True)
        self.assertFalse(Path(renamed).exists())

    async def test_removing_a_directory_without_recursive_fails(self) -> None:
        with self.assertRaises(IsADirectoryError):
            await self.fs.remove(str(self.root / "sub"))

    async def test_copy_between_local_paths(self) -> None:
        destination = str(self.root / "copy.txt")
        await self.fs.download(str(self.root / "notes.txt"), destination)
        self.assertEqual(Path(destination).read_text(encoding="utf-8"), "hello")

    async def test_relative_paths_resolve_against_root(self) -> None:
        entries = await self.fs.listdir("sub")
        self.assertEqual([entry.name for entry in entries], ["cash.conf"])


class FakeAsyncSftp:
    """Minimal stand-in with the coroutine-shaped API AsyncSSH exposes."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.removed: list[str] = []
        self.renamed: list[tuple[str, str]] = []

    async def listdir(self, path: str):
        prefix = path.rstrip("/") + "/"
        return sorted(name[len(prefix) :] for name in self.files if name.startswith(prefix))

    async def stat(self, path: str):
        if path not in self.files:
            raise OSError(path)
        return _Attrs(size=len(self.files[path]))

    async def lstat(self, path: str):
        return await self.stat(path)

    async def open(self, path: str, mode: str):
        return _FakeHandle(self.files, path, mode)

    async def remove(self, path: str):
        self.removed.append(path)
        self.files.pop(path, None)

    async def rmdir(self, path: str):
        await self.remove(path)

    async def rename(self, source: str, target: str):
        self.renamed.append((source, target))
        self.files[target] = self.files.pop(source)


class _Attrs:
    def __init__(self, size: int) -> None:
        self.size = size
        self.permissions = 0o100644
        self.mtime = 1_700_000_000
        self.uid = 1000


class _FakeHandle:
    def __init__(self, files: dict[str, bytes], path: str, mode: str) -> None:
        self.files = files
        self.path = path
        self.mode = mode
        self._buffer = bytearray(files.get(path, b""))
        self._position = 0

    async def read(self, size: int = -1):
        chunk = bytes(self._buffer[self._position : self._position + size]) if size and size > 0 else bytes(self._buffer[self._position :])
        self._position += len(chunk)
        return chunk

    async def write(self, data: bytes):
        self.files[self.path] = bytes(data)

    async def close(self):
        return None


class SftpFileSystemTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = FakeAsyncSftp({"/home/tc/cash.log": b"line\n"})
        self.fs = SftpFileSystem(self.client, "/home/tc")

    async def test_listdir_awaits_the_async_client(self) -> None:
        entries = await self.fs.listdir("/home/tc")
        self.assertEqual([entry.name for entry in entries], ["cash.log"])
        self.assertEqual(entries[0].size, 5)
        self.assertTrue(entries[0].permissions.startswith("-rw"))

    async def test_read_and_write(self) -> None:
        self.assertEqual(await self.fs.read_bytes("/home/tc/cash.log"), b"line\n")
        await self.fs.write_bytes("/home/tc/new.ini", b"[a]\n")
        self.assertEqual(self.client.files["/home/tc/new.ini"], b"[a]\n")

    async def test_tilde_expands_to_home(self) -> None:
        entries = await self.fs.listdir("~")
        self.assertEqual([entry.name for entry in entries], ["cash.log"])

    async def test_remove_and_rename(self) -> None:
        await self.fs.remove("/home/tc/cash.log")
        self.assertEqual(self.client.removed, ["/home/tc/cash.log"])
        self.client.files["/home/tc/a.txt"] = b"x"
        await self.fs.rename("/home/tc/a.txt", "/home/tc/b.txt")
        self.assertEqual(self.client.renamed, [("/home/tc/a.txt", "/home/tc/b.txt")])


class HelperTests(unittest.TestCase):
    def test_human_size(self) -> None:
        self.assertEqual(human_size(512), "512B")
        self.assertEqual(human_size(2048), "2.0K")
        self.assertEqual(human_size(5 * 1024 * 1024), "5.0M")
        self.assertEqual(human_size(3 * 1024**3), "3.0G")

    def test_mode_to_string(self) -> None:
        self.assertEqual(mode_to_string(0o40755), "drwxr-xr-x")
        self.assertEqual(mode_to_string(0o100644), "-rw-r--r--")

    def test_is_text_file(self) -> None:
        for name in ("cash.log", "ops.ini", "run.sh", "query.sql", "MANIFEST"):
            self.assertTrue(is_text_file(name), name)
        for name in ("photo.png", "archive.zip", "upload.part"):
            self.assertFalse(is_text_file(name), name)

    def test_parent_of_posix(self) -> None:
        self.assertEqual(parent_of("/home/tc/storage"), "/home/tc")
        self.assertEqual(parent_of("/"), "/")

    def test_join_posix(self) -> None:
        self.assertEqual(join("/home/tc", "logs"), "/home/tc/logs")

    def test_entry_info_display(self) -> None:
        entry = EntryInfo(name="a", path="/a", is_dir=True, is_link=False, size=0, modified=None)
        self.assertEqual(entry.display_size, "—")
        self.assertEqual(entry.display_modified, "—")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
