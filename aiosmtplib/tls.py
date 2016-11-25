try:
    import ssl
except ImportError:
    _has_tls = False  # pragma: no cover
else:
    _has_tls = True


def configure_tls_context(validate_certs=True, client_cert=None,
                          client_key=None):
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


class TLSOptions:

    def __init__(self, tls_context=None, validate_certs=True, client_cert=None,
                 client_key=None):
        self.validate(
            tls_context=tls_context, validate_certs=validate_certs,
            client_cert=client_cert, client_key=client_key)
        self.context = tls_context
        self.validate_certs = validate_certs
        self.client_cert = client_cert
        self.client_key = client_key

    def validate(self, tls_context=None, validate_certs=True, client_cert=None,
                 client_key=None):
        has_cert = client_cert or client_key
        if tls_context and has_cert:
            raise ValueError(
                'Either an SSLContext or a certificate/key must be provided')

    def get_context(self, tls_context=None, validate_certs=None,
                    client_cert=None, client_key=None):
        self.validate(
            tls_context=tls_context, validate_certs=validate_certs,
            client_cert=client_cert, client_key=client_key)

        if tls_context:
            context = tls_context
        elif not (client_cert or client_key) and self.context:
            context = self.context
        else:
            if validate_certs is None:
                validate_certs = self.validate_certs
            if client_cert is None:
                client_cert = self.client_cert
            if client_key is None:
                client_key = self.client_key

            context = configure_tls_context(
                validate_certs=validate_certs, client_cert=client_cert,
                client_key=client_key)

        return context
