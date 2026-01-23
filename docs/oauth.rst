.. _oauth:

OAuth2 Authentication (XOAUTH2)
===============================

aiosmtplib supports OAuth2 authentication via the XOAUTH2 mechanism, which is
used by Gmail, Outlook.com, and other providers that have deprecated traditional
password authentication.

The SMTP server must advertise ``XOAUTH2`` as a supported authentication method.

To use OAuth2, pass an async callable that returns a valid access token to the
``oauth_token_generator`` parameter.

.. note:: The ``oauth_token_generator`` parameter is mutually exclusive with
   ``password``. You cannot use both at the same time.


Basic Structure
---------------

.. code-block:: python

    import aiosmtplib

    async def get_access_token() -> str:
        # Your token refresh logic here
        return "your_access_token"

    await aiosmtplib.send(
        message,
        hostname="smtp.gmail.com",
        port=465,
        use_tls=True,
        username="your.email@gmail.com",
        oauth_token_generator=get_access_token,
    )


Token Expiry and Refresh
------------------------

OAuth2 access tokens are short-lived (typically 1 hour). The callable passed
as ``oauth_token_generator`` is responsible for returning a valid, non-expired
token each time it is called. It will be called immediately before the
``XOAUTH2`` authentication command is sent to the server.

**Your generator must handle expiry**

aiosmtplib does not track token expiry times or automatically retry on
authentication failure. Your callable should check if the token is expired
and refresh it before returning. Some libraries (e.g. ``google-auth``,
documented below) will handle this.


Gmail Example
-------------

Gmail allows OAuth2 for SMTP access. You'll need to create a project in the
`Google Cloud Console <https://console.cloud.google.com/>`_, and obtain OAuth2
credentials.

The ``google-auth`` library provides credential management with automatic token
refresh.

.. code-block:: python

    import asyncio
    from email.message import EmailMessage

    import aiosmtplib
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    # Load your credentials (obtained via OAuth flow)
    credentials = Credentials(
        token="ya29.access_token",
        refresh_token="1//refresh_token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="your_client_id.apps.googleusercontent.com",
        client_secret="your_client_secret",
    )

    async def get_gmail_token() -> str:
        """Return a valid access token, refreshing if needed."""
        if not credentials.valid:
            # google-auth is synchronous, so run in a thread
            await asyncio.to_thread(credentials.refresh, Request())
        return credentials.token

    async def send_email():
        message = EmailMessage()
        message["From"] = "your.email@gmail.com"
        message["To"] = "recipient@example.com"
        message["Subject"] = "Hello from aiosmtplib!"
        message.set_content("Sent using OAuth2 authentication.")

        await aiosmtplib.send(
            message,
            hostname="smtp.gmail.com",
            port=465,
            use_tls=True,
            username="your.email@gmail.com",
            oauth_token_generator=get_gmail_token,
        )

    asyncio.run(send_email())


Outlook / Microsoft 365 Example
-------------------------------

Microsoft requires OAuth2 for SMTP authentication. See the
`official Microsoft documentation
<https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth>`_
for setup instructions.

The ``msal`` library provides credential management with automatic token
refresh.

.. code-block:: python

    import asyncio
    from email.message import EmailMessage

    import aiosmtplib
    import msal

    # Your Azure AD app registration details
    CLIENT_ID = "your_client_id"
    TENANT_ID = "your_tenant_id"  # Or "common" for multi-tenant apps

    # Scope for SMTP sending
    SCOPES = ["https://outlook.office.com/SMTP.Send"]

    # Create MSAL public client app (for user authentication)
    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    )

    async def get_outlook_token() -> str:
        """Return a valid access token, refreshing silently if possible."""
        accounts = app.get_accounts()
        if accounts:
            # Try to get token silently (uses cached/refresh token)
            result = await asyncio.to_thread(
                app.acquire_token_silent, SCOPES, account=accounts[0]
            )
            if result and "access_token" in result:
                return result["access_token"]

        raise ValueError("No valid token available. Re-authentication required.")

    async def send_email():
        message = EmailMessage()
        message["From"] = "your.email@outlook.com"
        message["To"] = "recipient@example.com"
        message["Subject"] = "Hello from aiosmtplib!"
        message.set_content("Sent using OAuth2 authentication.")

        await aiosmtplib.send(
            message,
            hostname="smtp.office365.com",
            port=587,
            start_tls=True,
            username="your.email@outlook.com",
            oauth_token_generator=get_outlook_token,
        )

    asyncio.run(send_email())
