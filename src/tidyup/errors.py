"""Turn OS errors into short, friendly messages."""

from __future__ import annotations

import errno

# Windows error codes (exc.winerror). They only appear on Windows, but checking for them
# is harmless elsewhere because exc.winerror is simply absent there.
_WINERROR_SHARING_VIOLATION = 32  # "being used by another process"
_WINERROR_LOCK_VIOLATION = 33


def describe_os_error(exc: OSError) -> str:
    winerror = getattr(exc, "winerror", None)
    if winerror in (_WINERROR_SHARING_VIOLATION, _WINERROR_LOCK_VIOLATION):
        return "file is open in another program"
    if isinstance(exc, PermissionError):
        return "permission denied"
    if isinstance(exc, FileNotFoundError):
        return "file disappeared before it could be moved"
    if exc.errno == errno.ENOSPC:
        return "disk is full"
    if exc.errno == errno.ENAMETOOLONG:
        return "path is too long"
    return exc.strerror or str(exc)
