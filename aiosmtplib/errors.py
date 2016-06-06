import smtplib

SMTPException = smtplib.SMTPException
SMTPServerDisconnected = smtplib.SMTPServerDisconnected
SMTPConnectError = smtplib.SMTPConnectError
SMTPResponseException = smtplib.SMTPResponseException
SMTPHeloError = smtplib.SMTPHeloError
SMTPDataError = smtplib.SMTPDataError
SMPTRecipientsRefused = smtplib.SMPTRecipientsRefused
SMTPSenderRefused = smtplib.SMTPSenderRefused
SMTPAuthenticationError = smtplib.SMTPAuthenticationError


class SMTPRecipientRefused(SMTPException):
    '''
    smtplib only raises errors when multiple recipients are refused.
    '''
    def __init__(self, code, message, recipient):
        self.code = code
        self.message = message
        self.recipient = recipient
        self.args = (code, message, recipient,)
