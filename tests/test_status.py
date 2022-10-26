"""
Test status import shim.
"""

from aiosmtplib.status import SMTPStatus as OldImportSMTPStatus
from aiosmtplib.typing import SMTPStatus


def test_status_import() -> None:
    assert OldImportSMTPStatus is SMTPStatus
