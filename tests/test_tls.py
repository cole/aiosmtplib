import ssl

import pytest

from aiosmtplib import tls


@pytest.mark.skip("Support for SSL-less python isn't working yet")
def test_configure_tls_context_with_no_ssl_module_raises(monkeypatch):
    monkeypatch.setattr(tls, '_has_tls', False)

    with pytest.raises(RuntimeError):
        tls.configure_tls_context()


def test_configure_with_no_args_works():
    context = tls.configure_tls_context()

    assert isinstance(context, ssl.SSLContext)


def test_configure_with_validate_certs():
    context = tls.configure_tls_context(validate_certs=True)

    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_configure_without_validate_certs():
    context = tls.configure_tls_context(validate_certs=False)

    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_NONE
    assert context.check_hostname is False


def test_configure_with_cert_chain():
    """
    Just checks that the certs don't error, not that they're actually loaded.
    TODO: improve.
    """
    context = tls.configure_tls_context(
        client_cert='tests/certs/selfsigned.crt',
        client_key='tests/certs/selfsigned.key')

    assert isinstance(context, ssl.SSLContext)
