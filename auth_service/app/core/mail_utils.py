import os
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from pydantic import EmailStr
from typing import List

# SMTP Configuration from Environment
class Envs:
    # 1. Authentication Credentials (your primary Gmail account used to log in to SMTP)
    MAIL_USERNAME = os.getenv("SMTP_USERNAME", "kartikkalra2705@gmail.com")
    MAIL_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    
    # 2. Visible Sender Header (e.g. contact@relaypost.me, authorized under Gmail "Send mail as")
    MAIL_FROM = os.getenv("SMTP_FROM", os.getenv("MAIL_FROM", "no-reply@relaypost.me"))
    MAIL_FROM_NAME = os.getenv("SMTP_FROM_NAME", "RelayPost")
    
    # 3. SMTP Server settings
    MAIL_PORT = int(os.getenv("SMTP_PORT", "587"))
    MAIL_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    FRONTEND_URL = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")[0]
    
    # SSL/TLS Flags
    MAIL_STARTTLS = os.getenv("SMTP_STARTTLS", "True").lower() in ("true", "1")
    MAIL_SSL_TLS = os.getenv("SMTP_SSL_TLS", "False").lower() in ("true", "1")

conf = ConnectionConfig(
    MAIL_USERNAME=Envs.MAIL_USERNAME,
    MAIL_PASSWORD=Envs.MAIL_PASSWORD,
    MAIL_FROM=Envs.MAIL_FROM,
    MAIL_PORT=Envs.MAIL_PORT,
    MAIL_SERVER=Envs.MAIL_SERVER,
    MAIL_FROM_NAME=Envs.MAIL_FROM_NAME,
    MAIL_STARTTLS=Envs.MAIL_STARTTLS,
    MAIL_SSL_TLS=Envs.MAIL_SSL_TLS,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=os.getenv("SMTP_VALIDATE_CERTS", "False").lower() in ("true", "1")
)

async def send_invite_email(email: str, token: str):
    invite_url = f"{Envs.FRONTEND_URL}/auth/invite/{token}"
    
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; rounded-xl: 16px;">
        <h2 style="color: #4f46e5;">Welcome to RelayPost</h2>
        <p>You have been invited to join the RelayPost platform as a team member.</p>
        <p>Please click the button below to set your password and complete your registration:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{invite_url}" style="background-color: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">Join Workspace</a>
        </div>
        <p style="font-size: 12px; color: #64748b;">If the button doesn't work, copy and paste this link into your browser:</p>
        <p style="font-size: 12px; color: #4f46e5;">{invite_url}</p>
        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
        <p style="font-size: 10px; color: #94a3b8;">This invitation will expire in 48 hours.</p>
    </div>
    """

    message = MessageSchema(
        subject="Invitation to join RelayPost",
        recipients=[email],
        body=html,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    try:
        await fm.send_message(message)
        print(f"SUCCESS: Invite email sent to {email}")
        return True
    except Exception as e:
        print(f"ERROR: Failed to send email to {email}: {e}")
        # Log the link anyway for the user in the console
        print(f"DEBUG: Invitation Link: {invite_url}")
        return False

async def send_verification_email(email: str, token: str):
    verify_url = f"{Envs.FRONTEND_URL}/verify?token={token}"
    
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; rounded-xl: 16px;">
        <h2 style="color: #4f46e5;">Verify your Email for RelayPost</h2>
        <p>Thank you for registering. Please click the button below to verify your email and securely access your intelligence dashboard:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{verify_url}" style="background-color: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">Verify Email</a>
        </div>
        <p style="font-size: 12px; color: #64748b;">If the button doesn't work, copy and paste this link into your browser:</p>
        <p style="font-size: 12px; color: #4f46e5;">{verify_url}</p>
    </div>
    """

    message = MessageSchema(
        subject="Verify your RelayPost Account",
        recipients=[email],
        body=html,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    try:
        await fm.send_message(message)
        print(f"SUCCESS: Verification email sent to {email}")
        return True
    except Exception as e:
        print(f"ERROR: Failed to send email to {email}: {e}")
        # Log the link anyway for the user in the console
        print(f"DEBUG: Verification Link: {verify_url}")
        return False

async def send_password_reset_otp_email(email: str, otp: str):
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; rounded-xl: 16px;">
        <h2 style="color: #4f46e5;">Reset Your Password</h2>
        <p>We received a request to reset your password for your RelayPost account.</p>
        <p>Your one-time password (OTP) is:</p>
        <div style="text-align: center; margin: 30px 0;">
            <div style="display: inline-block; background-color: #f1f5f9; color: #0f172a; padding: 16px 32px; border-radius: 8px; font-weight: 900; font-size: 32px; letter-spacing: 8px;">
                {otp}
            </div>
        </div>
        <p style="font-size: 14px; color: #475569;">Enter this code on the password reset page to securely set a new password.</p>
        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
        <p style="font-size: 12px; color: #94a3b8;">This code is valid for 10 minutes. If you did not request this reset, you can safely ignore this email.</p>
    </div>
    """

    message = MessageSchema(
        subject="Your RelayPost Password Reset OTP",
        recipients=[email],
        body=html,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    try:
        await fm.send_message(message)
        print(f"SUCCESS: Reset OTP email sent to {email}")
        return True
    except Exception as e:
        print(f"ERROR: Failed to send reset OTP email to {email}: {e}")
        print(f"DEBUG: Reset OTP for {email}: {otp}")
        return False


# ── Subscription Emails ───────────────────────────────────────────────────────

def _base_style():
    return "font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 600px; margin: auto; background: #ffffff;"

def _btn(url: str, text: str, color: str = "#4f46e5") -> str:
    return f'<div style="text-align:center;margin:28px 0;"><a href="{url}" style="background:{color};color:#fff;padding:13px 28px;text-decoration:none;border-radius:8px;font-weight:700;font-size:15px;">{text}</a></div>'


async def send_trial_ending_email(email: str, tier: str, days_left: int):
    url = f"{Envs.FRONTEND_URL}/subscription"
    tier_label = tier.title()
    html = f"""
    <div style="{_base_style()} padding: 32px; border: 1px solid #e2e8f0;">
        <h2 style="color:#4f46e5;margin-bottom:8px;">Your {tier_label} trial ends in {days_left} day(s)</h2>
        <p style="color:#475569;">Your free trial of <strong>RelayPost {tier_label}</strong> is coming to an end.
        Your payment method will be automatically charged when the trial ends — no action needed if you want to continue.</p>
        <p style="color:#475569;">If you'd like to cancel before being charged, you can do so from your subscription settings.</p>
        {_btn(url, "Manage Subscription")}
        <hr style="border:0;border-top:1px solid #e2e8f0;margin:24px 0;">
        <p style="font-size:12px;color:#94a3b8;">RelayPost · <a href="{Envs.FRONTEND_URL}/pricing" style="color:#4f46e5;">View Plans</a></p>
    </div>"""
    msg = MessageSchema(subject=f"Your RelayPost {tier_label} trial ends in {days_left} day(s)", recipients=[email], body=html, subtype=MessageType.html)
    try:
        await FastMail(conf).send_message(msg)
    except Exception as e:
        print(f"ERROR send_trial_ending_email: {e}")


async def send_payment_failed_email(email: str, tier: str, retry_count: int, grace_end_date: str):
    url = f"{Envs.FRONTEND_URL}/subscription"
    tier_label = tier.title()
    html = f"""
    <div style="{_base_style()} padding: 32px; border: 1px solid #fca5a5;">
        <h2 style="color:#dc2626;margin-bottom:8px;">Payment failed for your {tier_label} plan</h2>
        <p style="color:#475569;">We were unable to charge your payment method for your <strong>RelayPost {tier_label}</strong> subscription.
        This is attempt <strong>{retry_count}</strong>.</p>
        <p style="color:#475569;">You have a <strong>3-day grace period</strong> (until {grace_end_date}) to update your payment method.
        If payment is not resolved by then, your plan will be downgraded to Free.</p>
        {_btn(url, "Update Payment Method", "#dc2626")}
        <p style="font-size:12px;color:#94a3b8;">You can still access your {tier_label} features during the grace period.</p>
    </div>"""
    msg = MessageSchema(subject=f"Action required: Payment failed for RelayPost {tier_label}", recipients=[email], body=html, subtype=MessageType.html)
    try:
        await FastMail(conf).send_message(msg)
    except Exception as e:
        print(f"ERROR send_payment_failed_email: {e}")


async def send_subscription_expired_email(email: str, tier: str, reason: str = ""):
    url = f"{Envs.FRONTEND_URL}/pricing"
    tier_label = tier.title()
    reason_text = {
        "trial_ended": "Your free trial ended without an active payment method.",
        "cancelled": "Your subscription period ended after you cancelled autopay.",
        "payment_failed": "We were unable to process your payment after multiple attempts.",
    }.get(reason, "Your subscription has ended.")
    html = f"""
    <div style="{_base_style()} padding: 32px; border: 1px solid #e2e8f0;">
        <h2 style="color:#475569;margin-bottom:8px;">Your {tier_label} plan has ended</h2>
        <p style="color:#475569;">{reason_text}</p>
        <p style="color:#475569;">You've been moved to the <strong>Free plan</strong>. You can resubscribe at any time to restore access to premium features.</p>
        {_btn(url, "View Plans & Resubscribe")}
    </div>"""
    msg = MessageSchema(subject=f"Your RelayPost {tier_label} plan has ended", recipients=[email], body=html, subtype=MessageType.html)
    try:
        await FastMail(conf).send_message(msg)
    except Exception as e:
        print(f"ERROR send_subscription_expired_email: {e}")


async def send_payment_success_email(email: str, tier: str, next_billing_date: str, amount_paise: int):
    url = f"{Envs.FRONTEND_URL}/subscription"
    tier_label = tier.title()
    amount_inr = amount_paise // 100
    html = f"""
    <div style="{_base_style()} padding: 32px; border: 1px solid #bbf7d0;">
        <h2 style="color:#16a34a;margin-bottom:8px;">Payment confirmed — {tier_label} active ✓</h2>
        <p style="color:#475569;">Your payment of <strong>₹{amount_inr}</strong> for <strong>RelayPost {tier_label}</strong> was successful.</p>
        <p style="color:#475569;">Your next billing date is <strong>{next_billing_date}</strong>.</p>
        {_btn(url, "View Subscription", "#16a34a")}
    </div>"""
    msg = MessageSchema(subject=f"Payment confirmed — RelayPost {tier_label}", recipients=[email], body=html, subtype=MessageType.html)
    try:
        await FastMail(conf).send_message(msg)
    except Exception as e:
        print(f"ERROR send_payment_success_email: {e}")


async def send_subscription_cancelled_email(email: str, tier: str, end_date: str):
    url = f"{Envs.FRONTEND_URL}/subscription"
    tier_label = tier.title()
    html = f"""
    <div style="{_base_style()} padding: 32px; border: 1px solid #e2e8f0;">
        <h2 style="color:#475569;margin-bottom:8px;">Autopay cancelled — access until {end_date}</h2>
        <p style="color:#475569;">You've turned off autopay for your <strong>RelayPost {tier_label}</strong> plan.
        You'll continue to have full access until <strong>{end_date}</strong>, after which you'll be moved to the Free plan.</p>
        <p style="color:#475569;">Changed your mind? Reactivate your subscription anytime before that date.</p>
        {_btn(url, "Reactivate Subscription")}
    </div>"""
    msg = MessageSchema(subject=f"Autopay cancelled — RelayPost {tier_label} active until {end_date}", recipients=[email], body=html, subtype=MessageType.html)
    try:
        await FastMail(conf).send_message(msg)
    except Exception as e:
        print(f"ERROR send_subscription_cancelled_email: {e}")


# ── Weekly Digest Email ───────────────────────────────────────────────────────

async def send_weekly_digest_email(
    email: str,
    display_name: str,
    digest: dict,
    opt_out_url: str,
    frontend_url: str,
) -> bool:
    """
    Sends the full weekly digest as a rich, newspaper-style HTML email.
    Includes executive summary, top articles, top news, What to Watch, opt-out link.
    """
    week_label       = digest.get("week_label", "This Week")
    executive_summary = digest.get("executive_summary", "")
    major_themes     = digest.get("major_themes", "")
    emerging_signals = digest.get("emerging_signals", "")
    editors_note     = digest.get("editors_note", "")
    stat_of_week     = digest.get("stat_of_week", "")
    top_articles     = digest.get("top_articles", [])[:5]
    top_news         = digest.get("top_news", [])[:5]
    what_to_watch    = digest.get("what_to_watch", [])[:3]

    # ── Build article cards ───────────────────────────────────────────────────
    def _article_card(a: dict, index: int) -> str:
        cat       = a.get("category", "General")
        title     = a.get("title", "")
        excerpt   = (a.get("excerpt", ""))[:180]
        slug      = a.get("slug", "")
        url_      = f"{frontend_url}/article/{slug}" if slug else frontend_url
        img       = a.get("hero_image", "")
        img_block = (
            f'<img src="{img}" alt="" style="width:100%;height:160px;object-fit:cover;border-radius:8px 8px 0 0;display:block;" />'
            if img else
            f'<div style="width:100%;height:6px;background:linear-gradient(90deg,#4f46e5,#7c3aed);border-radius:8px 8px 0 0;"></div>'
        )
        return f"""
        <div style="border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:16px;font-family:inherit;">
          {img_block}
          <div style="padding:16px;">
            <span style="display:inline-block;background:#ede9fe;color:#6d28d9;font-size:10px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;padding:3px 10px;border-radius:100px;margin-bottom:10px;">{cat}</span>
            <h3 style="margin:0 0 8px;font-size:16px;font-weight:700;color:#0f172a;line-height:1.4;">
              <a href="{url_}" style="color:#0f172a;text-decoration:none;">{title}</a>
            </h3>
            <p style="margin:0 0 12px;font-size:13px;color:#64748b;line-height:1.6;">{excerpt}…</p>
            <a href="{url_}" style="font-size:12px;font-weight:700;color:#4f46e5;text-decoration:none;letter-spacing:0.05em;">Read full article →</a>
          </div>
        </div>"""

    articles_html = "".join(_article_card(a, i) for i, a in enumerate(top_articles))

    # ── Build news list ───────────────────────────────────────────────────────
    def _news_row(n: dict) -> str:
        title_  = n.get("title", "")
        source  = n.get("source", "")
        cat     = n.get("category", "")
        slug    = n.get("slug", "")
        url_    = f"{frontend_url}/news/{slug}" if slug else frontend_url
        return f"""
        <tr>
          <td style="padding:12px 0;border-bottom:1px solid #f1f5f9;">
            <div style="display:flex;align-items:flex-start;gap:10px;">
              <div style="flex:1;">
                <p style="margin:0 0 4px;font-size:14px;font-weight:600;color:#1e293b;line-height:1.4;">
                  <a href="{url_}" style="color:#1e293b;text-decoration:none;">{title_}</a>
                </p>
                <p style="margin:0;font-size:11px;color:#94a3b8;">{source} · {cat}</p>
              </div>
            </div>
          </td>
        </tr>"""

    news_html = "".join(_news_row(n) for n in top_news)

    # ── Build What to Watch ───────────────────────────────────────────────────
    def _watch_card(w: dict, i: int) -> str:
        colors = ["#4f46e5", "#7c3aed", "#0ea5e9"]
        color  = colors[i % len(colors)]
        return f"""
        <tr>
          <td style="padding:10px 0;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td width="32" valign="top">
                  <div style="width:28px;height:28px;border-radius:50%;background:{color};color:#fff;font-size:12px;font-weight:900;text-align:center;line-height:28px;">{i+1}</div>
                </td>
                <td style="padding-left:12px;">
                  <p style="margin:0 0 2px;font-size:13px;font-weight:700;color:#1e293b;">{w.get('title','')}</p>
                  <p style="margin:0;font-size:12px;color:#64748b;line-height:1.5;">{w.get('description','')}</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    watch_html = "".join(_watch_card(w, i) for i, w in enumerate(what_to_watch))

    # ── Stat of the week block ────────────────────────────────────────────────
    stat_block = ""
    if stat_of_week:
        stat_parts = stat_of_week.split("—", 1) if "—" in stat_of_week else stat_of_week.split("-", 1)
        stat_num  = stat_parts[0].strip()
        stat_desc = stat_parts[1].strip() if len(stat_parts) > 1 else ""
        stat_block = f"""
        <div style="background:linear-gradient(135deg,#4f46e5,#7c3aed);border-radius:12px;padding:24px;margin:24px 0;text-align:center;">
          <p style="margin:0 0 6px;font-size:36px;font-weight:900;color:#fff;letter-spacing:-0.02em;">{stat_num}</p>
          <p style="margin:0;font-size:13px;color:rgba(255,255,255,0.8);line-height:1.5;">{stat_desc}</p>
        </div>"""

    # ── Themes as bullets ─────────────────────────────────────────────────────
    def _bullets(text: str) -> str:
        lines = [l.strip().lstrip("•- ") for l in text.split("\n") if l.strip() and not l.strip().startswith("#")]
        return "".join(
            f'<li style="margin-bottom:8px;font-size:13px;color:#475569;line-height:1.6;">{l}</li>'
            for l in lines if l
        )

    themes_html  = _bullets(major_themes)
    signals_html = _bullets(emerging_signals)

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>RelayPost Weekly Digest — {week_label}</title>
</head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;">
<tr><td align="center" style="padding:24px 16px;">

  <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

    <!-- MASTHEAD -->
    <tr>
      <td style="background:linear-gradient(135deg,#1e1b4b 0%,#312e81 50%,#4c1d95 100%);border-radius:16px 16px 0 0;padding:32px 36px;">
        <p style="margin:0 0 8px;font-size:10px;font-weight:900;letter-spacing:0.2em;text-transform:uppercase;color:rgba(255,255,255,0.5);">Weekly Intelligence Digest</p>
        <h1 style="margin:0 0 8px;font-size:28px;font-weight:900;color:#ffffff;letter-spacing:-0.02em;">RelayPost</h1>
        <p style="margin:0;font-size:13px;color:rgba(255,255,255,0.6);">{week_label} · Curated for {display_name}</p>
      </td>
    </tr>

    <!-- EXECUTIVE SUMMARY -->
    <tr>
      <td style="background:#ffffff;padding:28px 36px 20px;">
        <p style="margin:0 0 8px;font-size:10px;font-weight:900;letter-spacing:0.15em;text-transform:uppercase;color:#6d28d9;">Executive Summary</p>
        <p style="margin:0;font-size:16px;color:#1e293b;line-height:1.7;font-style:italic;border-left:3px solid #6d28d9;padding-left:16px;">{executive_summary}</p>
      </td>
    </tr>

    <!-- STAT OF THE WEEK -->
    {"<tr><td style='background:#fff;padding:0 36px;'>" + stat_block + "</td></tr>" if stat_block else ""}

    <!-- TOP ARTICLES -->
    {f'''
    <tr>
      <td style="background:#ffffff;padding:20px 36px 8px;">
        <p style="margin:0 0 16px;font-size:10px;font-weight:900;letter-spacing:0.15em;text-transform:uppercase;color:#0f172a;">Top Articles This Week</p>
        {articles_html}
      </td>
    </tr>''' if articles_html else ""}

    <!-- MAJOR THEMES -->
    {f'''
    <tr>
      <td style="background:#f8fafc;padding:24px 36px;">
        <p style="margin:0 0 12px;font-size:10px;font-weight:900;letter-spacing:0.15em;text-transform:uppercase;color:#0f172a;">Major Themes</p>
        <ul style="margin:0;padding-left:16px;">{themes_html}</ul>
      </td>
    </tr>''' if themes_html else ""}

    <!-- TOP NEWS -->
    {f'''
    <tr>
      <td style="background:#ffffff;padding:24px 36px;">
        <p style="margin:0 0 12px;font-size:10px;font-weight:900;letter-spacing:0.15em;text-transform:uppercase;color:#0f172a;">Top News</p>
        <table width="100%" cellpadding="0" cellspacing="0">{news_html}</table>
      </td>
    </tr>''' if news_html else ""}

    <!-- EMERGING SIGNALS -->
    {f'''
    <tr>
      <td style="background:#f0fdf4;padding:24px 36px;">
        <p style="margin:0 0 12px;font-size:10px;font-weight:900;letter-spacing:0.15em;text-transform:uppercase;color:#16a34a;">Emerging Signals</p>
        <ul style="margin:0;padding-left:16px;">{signals_html}</ul>
      </td>
    </tr>''' if signals_html else ""}

    <!-- WHAT TO WATCH -->
    {f'''
    <tr>
      <td style="background:#ffffff;padding:24px 36px;">
        <p style="margin:0 0 12px;font-size:10px;font-weight:900;letter-spacing:0.15em;text-transform:uppercase;color:#0f172a;">What to Watch Next Week</p>
        <table width="100%" cellpadding="0" cellspacing="0">{watch_html}</table>
      </td>
    </tr>''' if watch_html else ""}

    <!-- EDITOR'S NOTE -->
    {f'''
    <tr>
      <td style="background:#faf5ff;border-top:1px solid #ede9fe;padding:24px 36px;">
        <p style="margin:0 0 6px;font-size:10px;font-weight:900;letter-spacing:0.15em;text-transform:uppercase;color:#7c3aed;">Editor's Note</p>
        <p style="margin:0;font-size:14px;color:#581c87;line-height:1.7;font-style:italic;">"{editors_note}"</p>
      </td>
    </tr>''' if editors_note else ""}

    <!-- CTA -->
    <tr>
      <td style="background:#1e1b4b;padding:28px 36px;border-radius:0 0 16px 16px;text-align:center;">
        <a href="{frontend_url}/profile" style="display:inline-block;background:#6d28d9;color:#fff;font-size:13px;font-weight:700;padding:12px 28px;border-radius:8px;text-decoration:none;margin-bottom:20px;">View Full Digest Online →</a>
        <p style="margin:0;font-size:11px;color:rgba(255,255,255,0.4);">
          RelayPost · Published every Sunday<br/>
          <a href="{opt_out_url}" style="color:rgba(255,255,255,0.4);text-decoration:underline;">Unsubscribe from digest emails</a>
          &nbsp;·&nbsp;
          <a href="{frontend_url}/pricing" style="color:rgba(255,255,255,0.4);text-decoration:underline;">Manage subscription</a>
        </p>
      </td>
    </tr>

  </table>
</td></tr>
</table>
</body>
</html>"""

    msg = MessageSchema(
        subject=f"Your RelayPost Weekly Digest — {week_label}",
        recipients=[email],
        body=html,
        subtype=MessageType.html,
    )
    fm = FastMail(conf)
    try:
        await fm.send_message(msg)
        print(f"[DIGEST EMAIL] Sent to {email}")
        return True
    except Exception as e:
        print(f"[DIGEST EMAIL ERROR] Failed for {email}: {e}")
        return False


