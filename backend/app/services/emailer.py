"""Sending transactional email.

Deliberately provider-agnostic and failure-tolerant, in the same spirit as the
LLM layer: configure a provider and real email goes out; configure nothing and
the message is logged instead, so the whole signup flow still works on a
laptop with no internet and no API key.

Set either:
  * ``RESEND_API_KEY``  — simplest to set up, generous free tier, or
  * ``SMTP_HOST`` / ``SMTP_PORT`` / ``SMTP_USER`` / ``SMTP_PASSWORD``
plus ``MAIL_FROM`` (an address on a domain you control and have verified).
"""
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger("eaios.mail")


def is_configured() -> bool:
    return bool(settings.RESEND_API_KEY or (settings.SMTP_HOST and settings.MAIL_FROM))


def _send_resend(to: str, subject: str, text: str, html: str) -> bool:
    import httpx

    r = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        json={"from": settings.MAIL_FROM or "EAIOS <onboarding@resend.dev>",
              "to": [to], "subject": subject, "text": text, "html": html},
        timeout=15, trust_env=False,          # a host proxy must not break this
    )
    r.raise_for_status()
    return True


def _send_smtp(to: str, subject: str, text: str, html: str) -> bool:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.MAIL_FROM
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
        s.starttls()
        if settings.SMTP_USER:
            s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        s.send_message(msg)
    return True


def send(to: str, subject: str, text: str, html: str = "") -> bool:
    """Best-effort send. Returns True if it left the building."""
    html = html or f"<pre style='font:14px system-ui'>{text}</pre>"
    try:
        if settings.RESEND_API_KEY:
            return _send_resend(to, subject, text, html)
        if settings.SMTP_HOST and settings.MAIL_FROM:
            return _send_smtp(to, subject, text, html)
    except Exception as exc:  # noqa: BLE001 — never fail a signup because mail is down
        log.warning("email send failed to %s: %s", to, exc)
        return False
    log.info("[no mail provider configured] would send to %s: %s\n%s", to, subject, text)
    return False


def send_verification_code(to: str, code: str, company: str) -> bool:
    subject = f"{code} is your EAIOS verification code"
    text = (
        f"Your verification code for {company} is {code}.\n\n"
        "It expires in 15 minutes. If you didn't create this workspace, ignore this email."
    )
    html = f"""
    <div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:480px">
      <h2 style="margin:0 0 4px">Verify your email</h2>
      <p style="color:#555;margin:0 0 18px">
        Enter this code to finish setting up <b>{company}</b> on EAIOS.
      </p>
      <div style="font-size:32px;letter-spacing:8px;font-weight:700;
                  padding:14px 18px;background:#0b1020;color:#22d3ee;border-radius:12px;
                  text-align:center">{code}</div>
      <p style="color:#777;font-size:13px;margin-top:18px">
        The code expires in 15 minutes. If you didn't create this workspace you can ignore this email.
      </p>
    </div>"""
    return send(to, subject, text, html)
