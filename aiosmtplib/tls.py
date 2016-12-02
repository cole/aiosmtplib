try:
    import ssl
except ImportError:  # pragma: no cover
    _has_tls = False
else:
    _has_tls = True


def configure_tls_context(validate_certs: bool = True, client_cert: str = None,
                          client_key: str = None) -> ssl.SSLContext:
    if not _has_tls:
        raise RuntimeError('No SSL support in this Python')

    # SERVER_AUTH is what we want for a client side socket
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.check_hostname = bool(validate_certs)
    if validate_certs:
        context.verify_mode = ssl.CERT_REQUIRED
    else:
        context.verify_mode = ssl.CERT_NONE

    if client_cert and client_key:
        context.load_cert_chain(client_cert, keyfile=client_key)

    return context
