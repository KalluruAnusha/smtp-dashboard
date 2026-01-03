"""
smtp_handler.py

Defines a handler for aiosmtpd which forwards received messages to an async callback.
"""
from email import message_from_bytes
from aiosmtpd.handlers import Message
from aiosmtpd.smtp import Session
from aiosmtpd.controller import Controller
from email.message import EmailMessage
from typing import Callable, Awaitable, List
import asyncio


class ForwardingHandler:
    """
    aiosmtpd handler that forwards incoming raw messages to an async callback.

    callback signature: async def callback(envelope_from: str, rcpt_tos: List[str], message_bytes: bytes)
    """
    def __init__(self, callback: Callable[[str, List[str], bytes], Awaitable[None]]):
        self.callback = callback

    async def handle_DATA(self, server, session: Session, envelope):
        try:
            # envelope.content is bytes
            await self.callback(envelope.mail_from, envelope.rcpt_tos, envelope.content)
            return "250 Message accepted for delivery"
        except Exception as exc:
            # If processing failed, still accept so as to not block SMTP clients in a prototype.
            # In production consider queueing and proper error responses.
            print("Error processing message in handler:", exc)
            return "250 Message accepted (processing error)"
