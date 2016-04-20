import email.utils


def quote_address(address_string):
    """Quote a subset of the email addresses defined by RFC 821.

    Should be able to handle anything email.utils.parseaddr can handle.
    """
    display_name, address = email.utils.parseaddr(address_string)
    if (display_name, address) == ('', ''):
        # parseaddr couldn't parse it, use it as is and hope for the best.
        if address_string.strip().startswith('<'):
            return address_string
        else:
            return "<{}>".format(address_string)
    else:
        return "<{}>".format(address)


def extract_address(address_string):
    """Extracts the email address from a display name string.

    Should be able to handle anything email.utils.parseaddr can handle.
    """
    display_name, address = email.utils.parseaddr(address_string)
    if (display_name, address) == ('', ''):
        # parseaddr couldn't parse it, so use it as is.
        return address_string
    else:
        return address
