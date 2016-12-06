"""
SMTP status codes, as constants for code readability.
"""
import enum

__all__ = ('SMTPStatus',)


class SMTPStatus(enum.IntEnum):
    invalid_response = -1
    system_status_ok = 211
    help_message = 214
    ready = 220
    closing = 221
    auth_successful = 235
    completed = 250
    will_forward = 251
    cannot_vrfy = 252
    auth_continue = 334
    start_input = 354
    domain_unavailable = 421
    mailbox_unavailable = 450
    error_processing = 451
    insufficient_storage = 452
    unrecognized_command = 500
    unrecognized_parameters = 501
    command_not_implemented = 502
    bad_command_sequence = 503
    parameter_not_implemented = 504
    domain_does_not_accept_mail = 521
    access_denied = 530  # Sendmail specific
    mailbox_does_not_exist = 550
    user_not_local = 551
    storage_exceeded = 552
    mailbox_name_invalid = 553
    transaction_failed = 554
    syntax_error = 555
