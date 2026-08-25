"""Disk accounting and removal for a project's own storage folder.

Everything a project accumulates lives under a single directory
(`settings.project_dir()`): the copied source video, the analysis
transcript, and one folder per clip holding its cut/rendered/burned
outputs. Deleting a project therefore has to delete that tree too --
dropping only the database row would leave the biggest files on disk
(source videos run to hundreds of MB each) with nothing left in the UI
pointing at them.

Removal is deliberately non-fatal per file: on Windows a video the user
is previewing, or a file an in-flight ffmpeg still holds open, can't be
unlinked, and that must not abort the rest of the cleanup or leave the
history entry stuck. Whatever couldn't be removed is reported back so
the caller can say so instead of silently claiming success.
"""

from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class StorageDeletion:
    freed_bytes: int = 0
    failed_paths: list[str] = field(default_factory=list)

    def merge(self, other: "StorageDeletion") -> "StorageDeletion":
        return StorageDeletion(
            freed_bytes=self.freed_bytes + other.freed_bytes,
            failed_paths=[*self.failed_paths, *other.failed_paths],
        )


def directory_bytes(path: Path) -> int:
    """Total size of every file under `path`, skipping anything that can't be
    stat'd (a file deleted mid-walk, a broken link)."""
    total = 0
    if not path.is_dir():
        return 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def delete_directory(path: Path) -> StorageDeletion:
    if not path.exists():
        return StorageDeletion()

    before = directory_bytes(path)
    failed: list[str] = []

    def on_error(func, failed_path, _exc) -> None:
        # The common Windows case is a read-only bit rather than a real lock,
        # so clear it and retry once before giving up on this entry.
        try:
            os.chmod(failed_path, stat.S_IWRITE)
            func(failed_path)
        except OSError:
            failed.append(str(failed_path))

    shutil.rmtree(path, onexc=on_error)
    remaining = directory_bytes(path)
    return StorageDeletion(freed_bytes=max(0, before - remaining), failed_paths=failed)
