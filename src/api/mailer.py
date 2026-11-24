"""
Outgoing email (password resets).

With SMTP configured, mail is sent on a background thread so the request
returns at once and its timing does not reveal whether the address exists.
Without SMTP (hatchery laptop, local development) the message is printed to
the server console instead, where the operator can copy the reset link.
"""

from __future__ import annotations

import smtplib
import ssl
import threading
from email.message import EmailMessage

from api.config import WebConfig


def _send(cfg: WebConfig, to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg['From'] = cfg.smtp_from
    msg['To'] = to
    msg['Subject'] = subject
    msg.set_content(body)
    try:
        if cfg.smtp_security == 'ssl':
            with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=20,
                                  context=ssl.create_default_context()) as s:
                if cfg.smtp_user:
                    s.login(cfg.smtp_user, cfg.smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20) as s:
                if cfg.smtp_security == 'starttls':
                    s.starttls(context=ssl.create_default_context())
                if cfg.smtp_user:
                    s.login(cfg.smtp_user, cfg.smtp_password)
                s.send_message(msg)
    except Exception as e:  # never surface SMTP failures to the requester
        print(f'[mail] could not send "{subject}": {type(e).__name__}: {e}')


def send_mail(cfg: WebConfig, to: str, subject: str, body: str) -> None:
    if not cfg.email_enabled:
        print('\n' + '-' * 64)
        print(f'[mail] SMTP is not configured; message for {to}:')
        print(f'Subject: {subject}\n\n{body}')
        print('-' * 64 + '\n')
        return
    threading.Thread(target=_send, args=(cfg, to, subject, body), daemon=True).start()
