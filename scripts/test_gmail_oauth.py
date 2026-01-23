#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "aiosmtplib",
#     "google-auth",
#     "google-auth-oauthlib",
# ]
#
# [tool.uv.sources]
# aiosmtplib = { path = ".." }
# ///
"""
Test script for Gmail XOAUTH2 authentication with aiosmtplib.

Usage:
    # Step 1: Get a refresh token (one-time setup)
    python test_gmail_oauth.py authorize \
        --client-id YOUR_CLIENT_ID \
        --client-secret YOUR_CLIENT_SECRET

    # Step 2: Send a test email
    python test_gmail_oauth.py send \
        --client-id YOUR_CLIENT_ID \
        --client-secret YOUR_CLIENT_SECRET \
        --refresh-token YOUR_REFRESH_TOKEN \
        --username YOUR_EMAIL@gmail.com \
        --to RECIPIENT@example.com

This script will send a test email using Gmail's SMTP server with OAuth2
authentication.

Run with: uv run test_gmail_oauth.py <command> [options]
"""

import argparse
import asyncio
from email.message import EmailMessage

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

import aiosmtplib

# Gmail SMTP scope
GMAIL_SCOPES = ["https://mail.google.com/"]

# Google OAuth2 token endpoint
TOKEN_URI = "https://oauth2.googleapis.com/token"


def authorize(client_id: str, client_secret: str) -> None:
    """Run the OAuth2 authorization flow to get a refresh token."""
    # Build client config for InstalledAppFlow
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=GMAIL_SCOPES)

    print("=" * 60)
    print("Gmail OAuth2 Authorization")
    print("=" * 60)
    print()
    print("Opening browser for authorization...")

    credentials = flow.run_local_server(port=8089)

    print()
    print("=" * 60)
    print("Authorization successful!")
    print("=" * 60)
    print()
    print(f"Access Token:  {credentials.token[:50]}...")
    print(f"Refresh Token: {credentials.refresh_token}")
    print(f"Expiry:        {credentials.expiry}")
    print()
    print("Save the refresh token above and use it with the 'send' command.")


async def send_test_email(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    username: str,
    to: str,
) -> None:
    """Send a test email using Gmail XOAUTH2."""
    # Create credentials object using google-auth
    credentials = Credentials(
        token=None,  # Will be refreshed
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
    )

    async def get_gmail_token() -> str:
        """Return a valid access token, refreshing if needed."""
        if not credentials.valid:
            print("Refreshing access token...")
            await asyncio.to_thread(credentials.refresh, Request())
            print(f"Got access token: {credentials.token[:20]}...")
        return credentials.token

    # Build the email message
    message = EmailMessage()
    message["From"] = username
    message["To"] = to
    message["Subject"] = "Test email from aiosmtplib XOAUTH2"
    message.set_content(
        "This is a test email sent using aiosmtplib with Gmail XOAUTH2 authentication.\n\n"
        "If you received this, the OAuth2 implementation is working correctly!"
    )

    print(f"Sending email from {username} to {to}...")

    # Send via Gmail SMTP with OAuth2
    response = await aiosmtplib.send(
        message,
        hostname="smtp.gmail.com",
        port=465,
        use_tls=True,
        username=username,
        oauth_token_generator=get_gmail_token,
    )

    print("Email sent successfully!")
    print(f"Server response: {response}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Gmail XOAUTH2 with aiosmtplib")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Authorize subcommand
    auth_parser = subparsers.add_parser(
        "authorize",
        help="Get a refresh token via OAuth2 authorization flow",
    )
    auth_parser.add_argument(
        "--client-id",
        required=True,
        help="Google OAuth2 client ID",
    )
    auth_parser.add_argument(
        "--client-secret",
        required=True,
        help="Google OAuth2 client secret",
    )

    # Send subcommand
    send_parser = subparsers.add_parser(
        "send",
        help="Send a test email using OAuth2",
    )
    send_parser.add_argument(
        "--client-id",
        required=True,
        help="Google OAuth2 client ID",
    )
    send_parser.add_argument(
        "--client-secret",
        required=True,
        help="Google OAuth2 client secret",
    )
    send_parser.add_argument(
        "--refresh-token",
        required=True,
        help="Google OAuth2 refresh token",
    )
    send_parser.add_argument(
        "--username",
        required=True,
        help="Sender email address (your Gmail address)",
    )
    send_parser.add_argument(
        "--to",
        required=True,
        help="Recipient email address",
    )

    args = parser.parse_args()

    if args.command == "authorize":
        authorize(args.client_id, args.client_secret)
    elif args.command == "send":
        asyncio.run(
            send_test_email(
                client_id=args.client_id,
                client_secret=args.client_secret,
                refresh_token=args.refresh_token,
                username=args.username,
                to=args.to,
            )
        )


if __name__ == "__main__":
    main()
