from datetime import datetime, timezone
from html import escape


def _layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <body style="margin:0;background:#f4f6f8;font-family:Arial,sans-serif;color:#17202a;">
    <div style="max-width:620px;margin:32px auto;background:#ffffff;border:1px solid #dfe4ea;">
      <div style="padding:22px 28px;background:#123b5d;color:#ffffff;">
        <h1 style="margin:0;font-size:22px;">{escape(title)}</h1>
      </div>
      <div style="padding:28px;line-height:1.6;">{body}</div>
      <div style="padding:16px 28px;border-top:1px solid #e9edf1;color:#6b7785;font-size:12px;">
        Automated message from ARASPL
      </div>
    </div>
  </body>
</html>"""


def reminder(name: str = "Admin") -> tuple[str, str]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    safe_name = escape(name)
    subject = "Scheduled reminder"
    body = (
        f"<p>Hello {safe_name},</p>"
        f"<p>This is the scheduled reminder generated at <strong>{now}</strong>.</p>"
        "<p>Please review this message and take any required action.</p>"
    )
    return subject, _layout(subject, body)


def welcome(name: str = "Admin") -> tuple[str, str]:
    subject = "Welcome"
    body = (
        f"<p>Hello {escape(name)},</p>"
        "<p>Welcome. This message was sent using the Microsoft Graph API.</p>"
    )
    return subject, _layout(subject, body)


def status(name: str = "Admin") -> tuple[str, str]:
    subject = "Automated status update"
    body = (
        f"<p>Hello {escape(name)},</p>"
        "<p>The scheduled email service is running normally.</p>"
    )
    return subject, _layout(subject, body)


TEMPLATES = {
    "reminder": reminder,
    "welcome": welcome,
    "status": status,
}


def render_template(template_name: str, name: str) -> tuple[str, str]:
    try:
        template = TEMPLATES[template_name.lower()]
    except KeyError as error:
        choices = ", ".join(sorted(TEMPLATES))
        raise ValueError(f"Unknown template '{template_name}'. Choose: {choices}") from error
    return template(name)