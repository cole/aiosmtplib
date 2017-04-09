"""
Tests covering SMTP configuration options.
"""
import pytest

from aiosmtplib import SMTP


def test_tls_context_and_cert_raises():
    with pytest.raises(ValueError):
        SMTP(use_tls=True, client_cert='foo.crt', tls_context=True)
