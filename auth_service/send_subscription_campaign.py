#!/usr/bin/env python3
"""
RelayPost Founding Member Subscription & Supporter Campaign Script
==================================================================
Allows administrators to send an exclusive invitation to existing users
to either:
1. Subscribe to the monthly basic plan (RelayPost Plus - ₹99/mo with 7-day free trial).
2. Make a direct one-time contribution (suggested ₹50, customizable by the user on checkout).

Features:
- Generates a signed, secure JWT token for 1-click auto-login & direct checkout.
- Direct checkout URLs open the payment gateway immediately without friction.
- High-converting, responsive HTML email design featuring both monthly subscription and direct one-time contribution options.
- Supports --contribution-amount <N> (default 50), --dry-run, --email <address>, --limit <N>, and --all flags.
"""

import os
import sys
import argparse
import asyncio
from datetime import timedelta
from typing import List, Optional

# Add auth_service root to sys.path so app modules import properly
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from dotenv import load_dotenv
load_dotenv()

# Auto-detect if running outside Docker where 'postgres' hostname does not resolve
import socket
db_url = os.environ.get("DATABASE_URL", "")
if "@postgres:" in db_url:
    try:
        socket.gethostbyname("postgres")
    except socket.gaierror:
        # Running directly on host machine, map postgres host to localhost
        os.environ["DATABASE_URL"] = db_url.replace("@postgres:", "@localhost:")

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models import models
from app.core.auth_deps import create_access_token

class Envs:
    MAIL_USERNAME = os.getenv("SMTP_USERNAME", "kartikkalra2705@gmail.com")
    MAIL_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    MAIL_FROM = os.getenv("SMTP_FROM", os.getenv("MAIL_FROM", "no-reply@relaypost.me"))
    MAIL_FROM_NAME = os.getenv("SMTP_FROM_NAME", "RelayPost")
    MAIL_PORT = int(os.getenv("SMTP_PORT", "587"))
    MAIL_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    FRONTEND_URL = os.getenv("FRONTEND_URL", os.getenv("CORS_ORIGINS", "https://relaypost.me")).split(",")[0]
    MAIL_STARTTLS = os.getenv("SMTP_STARTTLS", "True").lower() in ("true", "1")
    MAIL_SSL_TLS = os.getenv("SMTP_SSL_TLS", "False").lower() in ("true", "1")

FRONTEND_URL = Envs.FRONTEND_URL.rstrip("/")

try:
    from app.core.mail_utils import conf, FastMail, MessageSchema, MessageType
    HAS_FASTAPI_MAIL = True
except Exception:
    try:
        from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
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
        HAS_FASTAPI_MAIL = True
    except Exception:
        HAS_FASTAPI_MAIL = False
        conf = None
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

def build_campaign_html(
    display_name: str,
    checkout_url: str,
    pricing_url: str,
    contribution_url: str,
    contribution_amount: int = 50,
    token: Optional[str] = None
) -> str:
    """Generates an executive, mobile-responsive HTML email with both subscription and one-time contribution CTAs."""
    name = display_name if display_name and display_name.strip() else "Reader"

    # Construct preset contribution links with tracking parameters
    tok_param = f"&token={token}" if token else ""
    utm_base = "&utm_source=email_campaign&utm_medium=email&utm_campaign=founding_member"
    p25_url = f"{FRONTEND_URL}/checkout?type=contribution&amount=25{tok_param}{utm_base}&utm_content=contribution_25"
    p50_url = f"{FRONTEND_URL}/checkout?type=contribution&amount=50{tok_param}{utm_base}&utm_content=contribution_50"
    p100_url = f"{FRONTEND_URL}/checkout?type=contribution&amount=100{tok_param}{utm_base}&utm_content=contribution_100"
    p250_url = f"{FRONTEND_URL}/checkout?type=contribution&amount=250{tok_param}{utm_base}&utm_content=contribution_250"
    custom_url = f"{FRONTEND_URL}/checkout?type=contribution&custom=1{tok_param}{utm_base}&utm_content=contribution_custom"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Exclusive Founding Member & Supporter Invitation — RelayPost</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background-color: #0b0f19;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      color: #e2e8f0;
      -webkit-font-smoothing: antialiased;
    }}
    .email-container {{
      max-width: 600px;
      margin: 0 auto;
      background-color: #0f172a;
      border: 1px solid #1e293b;
      border-radius: 16px;
      overflow: hidden;
    }}
  </style>
</head>
<body style="margin: 0; padding: 24px 12px; background-color: #0b0f19;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
    <tr>
      <td align="center">
        <!-- Main Card Container -->
        <table role="presentation" class="email-container" width="100%" style="max-width: 600px; background-color: #0f172a; border: 1px solid #1e293b; border-radius: 16px;" cellspacing="0" cellpadding="0" border="0">
          
          <!-- Top Accent Bar -->
          <tr>
            <td style="height: 4px; background: linear-gradient(90deg, #4f46e5, #9333ea, #38bdf8);"></td>
          </tr>

          <!-- Header Section -->
          <tr>
            <td style="padding: 32px 32px 16px 32px; text-align: left;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td>
                    <span style="font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1.5px; color: #818cf8; background-color: rgba(99, 102, 241, 0.15); padding: 5px 12px; border-radius: 20px; border: 1px solid rgba(99, 102, 241, 0.3);">
                      ✦ Exclusive Reader Invitation
                    </span>
                  </td>
                </tr>
              </table>
              <h1 style="color: #ffffff; font-size: 26px; font-weight: 800; line-height: 1.25; margin: 20px 0 8px 0; letter-spacing: -0.5px;">
                Support RelayPost &amp; Unlock Full Intelligence
              </h1>
              <p style="color: #94a3b8; font-size: 15px; line-height: 1.5; margin: 0 0 24px 0;">
                Hi {name}, as one of our early readers, we invite you to support our independent newsroom and intelligence platform. Choose either a recurring founding membership or make a direct one-time contribution.
              </p>

              <!-- OPTION 1: Monthly Subscription Plan Card -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background: linear-gradient(135deg, rgba(79, 70, 229, 0.12) 0%, rgba(124, 58, 237, 0.12) 100%); border: 1px solid rgba(99, 102, 241, 0.35); border-radius: 12px; margin-bottom: 16px;">
                <tr>
                  <td style="padding: 20px 22px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td>
                          <span style="font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; color: #818cf8; background-color: rgba(99, 102, 241, 0.2); padding: 3px 8px; border-radius: 6px;">
                            Option A &bull; Subscription Plan
                          </span>
                        </td>
                        <td align="right">
                          <span style="font-size: 15px; font-weight: 800; color: #ffffff;">₹99<span style="font-size: 12px; color: #94a3b8; font-weight: 500;">/mo</span></span>
                        </td>
                      </tr>
                    </table>
                    <h3 style="color: #ffffff; font-size: 17px; font-weight: 700; margin: 12px 0 6px 0;">
                      RelayPost Plus (7-Day Free Trial)
                    </h3>
                    <p style="color: #94a3b8; font-size: 13px; line-height: 1.45; margin: 0 0 16px 0;">
                      Full daily AI syntheses, interactive Q&amp;A, ad-free reading, and Sunday intelligence digests. 100% free for the first 7 days.
                    </p>
                    <div>
                      <a href="{checkout_url}" style="display: inline-block; background-color: #4f46e5; color: #ffffff !important; text-decoration: none; font-weight: 700; font-size: 14px; padding: 12px 24px; border-radius: 8px;">
                        Activate 7-Day Free Trial (₹99/mo) &rarr;
                      </a>
                    </div>
                    <p style="color: #64748b; font-size: 11px; margin: 10px 0 0 0;">
                      🔒 Secure 1-click checkout &bull; Cancel anytime &bull; No charge until day 8
                    </p>
                  </td>
                </tr>
              </table>

              <!-- OPTION 2: Direct One-Time Contribution Card -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #1e293b; border: 1px solid #334155; border-radius: 12px; margin-bottom: 20px;">
                <tr>
                  <td style="padding: 20px 22px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td>
                          <span style="font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; color: #38bdf8; background-color: rgba(56, 189, 248, 0.15); padding: 3px 8px; border-radius: 6px;">
                            Option B &bull; One-Time Support
                          </span>
                        </td>
                        <td align="right">
                          <span style="font-size: 15px; font-weight: 800; color: #38bdf8;">₹{contribution_amount}<span style="font-size: 12px; color: #94a3b8; font-weight: 500;"> direct</span></span>
                        </td>
                      </tr>
                    </table>
                    <h3 style="color: #ffffff; font-size: 17px; font-weight: 700; margin: 12px 0 6px 0;">
                      Direct One-Time Contribution
                    </h3>
                    <p style="color: #94a3b8; font-size: 13px; line-height: 1.45; margin: 0 0 14px 0;">
                      Prefer not to subscribe? Support our mission directly with a single contribution. Default is ₹{contribution_amount}, and you can adjust the amount on checkout.
                    </p>
                    <div style="margin-bottom: 12px;">
                      <a href="{contribution_url}" style="display: inline-block; background-color: #0284c7; color: #ffffff !important; text-decoration: none; font-weight: 700; font-size: 14px; padding: 12px 24px; border-radius: 8px;">
                        Contribute ₹{contribution_amount} Once &rarr;
                      </a>
                    </div>
                    <!-- Preset chips row -->
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin-top: 8px;">
                      <tr>
                        <td style="color: #94a3b8; font-size: 12px; padding-right: 8px; font-weight: 600;">
                          Or choose:
                        </td>
                        <td style="padding: 2px 4px;">
                          <a href="{p25_url}" style="display: inline-block; background-color: #0f172a; border: 1px solid #475569; color: #e2e8f0 !important; text-decoration: none; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 6px;">₹25</a>
                        </td>
                        <td style="padding: 2px 4px;">
                          <a href="{p50_url}" style="display: inline-block; background-color: #0f172a; border: 1px solid #475569; color: #e2e8f0 !important; text-decoration: none; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 6px;">₹50</a>
                        </td>
                        <td style="padding: 2px 4px;">
                          <a href="{p100_url}" style="display: inline-block; background-color: #0f172a; border: 1px solid #475569; color: #e2e8f0 !important; text-decoration: none; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 6px;">₹100</a>
                        </td>
                        <td style="padding: 2px 4px;">
                          <a href="{p250_url}" style="display: inline-block; background-color: #0f172a; border: 1px solid #475569; color: #e2e8f0 !important; text-decoration: none; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 6px;">₹250</a>
                        </td>
                        <td style="padding: 2px 4px;">
                          <a href="{custom_url}" style="display: inline-block; background-color: #0f172a; border: 1px solid #475569; color: #e2e8f0 !important; text-decoration: none; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 6px;">Custom &rarr;</a>
                        </td>
                      </tr>
                    </table>
                    <p style="color: #64748b; font-size: 11px; margin: 10px 0 0 0;">
                      🔒 Direct Razorpay checkout &bull; No recurring mandate &bull; UPI &amp; Cards &bull; Customizable amount
                    </p>
                  </td>
                </tr>
              </table>

            </td>
          </tr>

          <!-- Divider -->
          <tr>
            <td style="padding: 0 32px;"><hr style="border: 0; border-top: 1px solid #1e293b; margin: 0;"></td>
          </tr>

          <!-- Crisp Founding Benefits Section -->
          <tr>
            <td style="padding: 24px 32px;">
              <h3 style="color: #f1f5f9; font-size: 16px; font-weight: 700; margin: 0 0 16px 0; text-transform: uppercase; letter-spacing: 0.5px;">
                What You Get as a Plus Member:
              </h3>

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom: 12px;">
                <tr>
                  <td width="36" valign="top" style="padding-top: 2px;">
                    <span style="font-size: 18px;">⚡</span>
                  </td>
                  <td>
                    <strong style="color: #ffffff; font-size: 14px;">Instant AI Syntheses & Q&A:</strong>
                    <div style="color: #94a3b8; font-size: 13px; line-height: 1.4; margin-top: 2px;">
                      40 executive summaries and 25 interactive deep-dives every single day.
                    </div>
                  </td>
                </tr>
              </table>

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom: 12px;">
                <tr>
                  <td width="36" valign="top" style="padding-top: 2px;">
                    <span style="font-size: 18px;">📬</span>
                  </td>
                  <td>
                    <strong style="color: #ffffff; font-size: 14px;">Curated Sunday Intelligence Digest:</strong>
                    <div style="color: #94a3b8; font-size: 13px; line-height: 1.4; margin-top: 2px;">
                      The week's highest-signal shifts and systemic analysis delivered directly to your inbox.
                    </div>
                  </td>
                </tr>
              </table>

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom: 12px;">
                <tr>
                  <td width="36" valign="top" style="padding-top: 2px;">
                    <span style="font-size: 18px;">🛡️</span>
                  </td>
                  <td>
                    <strong style="color: #ffffff; font-size: 14px;">Locked-In Early Adopter Pricing:</strong>
                    <div style="color: #94a3b8; font-size: 13px; line-height: 1.4; margin-top: 2px;">
                      Lock in ₹99/month for life with zero unexpected price increases.
                    </div>
                  </td>
                </tr>
              </table>

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td width="36" valign="top" style="padding-top: 2px;">
                    <span style="font-size: 18px;">🎯</span>
                  </td>
                  <td>
                    <strong style="color: #ffffff; font-size: 14px;">Custom Radar & Unlimited Topics:</strong>
                    <div style="color: #94a3b8; font-size: 13px; line-height: 1.4; margin-top: 2px;">
                      Follow all categories and bookmark essential intelligence for your workflow.
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Explore More Plans Box -->
          <tr>
            <td style="padding: 0 32px 28px 32px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #1e293b; border-radius: 12px; padding: 18px 20px;">
                <tr>
                  <td>
                    <p style="color: #cbd5e1; font-size: 13px; line-height: 1.5; margin: 0;">
                      Looking for annual savings (2 months free) or enterprise features like cross-article research mode?
                    </p>
                    <div style="margin-top: 8px;">
                      <a href="{pricing_url}" style="color: #818cf8; text-decoration: none; font-weight: 700; font-size: 13px;">
                        Explore all plans on our Pricing Page &rarr;
                      </a>
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding: 24px 32px; background-color: #0b1120; border-top: 1px solid #1e293b; text-align: center;">
              <p style="color: #64748b; font-size: 12px; margin: 0 0 6px 0;">
                RelayPost Intelligence &bull; Independent, High-Signal Journalism & Research
              </p>
              <p style="color: #475569; font-size: 11px; margin: 0;">
                You are receiving this because you have an active RelayPost account.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

def get_eligible_users(db: Session, target_email: Optional[str] = None, limit: Optional[int] = None) -> List[models.User]:
    """Retrieves active users eligible for the campaign (free tier or un-subscribed)."""
    query = db.query(models.User).filter(
        models.User.is_active == True,
        models.User.is_deleted == False
    )

    if target_email:
        query = query.filter(models.User.email == target_email)
    else:
        # If user has an existing active Plus or Pro subscription, exclude them
        query = query.outerjoin(models.Subscription).filter(
            (models.Subscription.id == None) |
            (models.Subscription.tier == models.SubscriptionTier.FREE) |
            (models.Subscription.status.in_([models.SubscriptionStatus.CANCELLED, models.SubscriptionStatus.EXPIRED]))
        )

    if limit:
        query = query.limit(limit)

    return query.all()

async def send_campaign_to_user(user: models.User, contribution_amount: int = 50, dry_run: bool = False) -> bool:
    """Generates direct checkout token and sends the invitation email."""
    # 1. Generate secure JWT token valid for 7 days
    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": role_val},
        expires_delta=timedelta(days=7)
    )

    # 2. Build target URLs with UTM tracking parameters
    utm_base = "&utm_source=email_campaign&utm_medium=email&utm_campaign=founding_member"
    checkout_url = f"{FRONTEND_URL}/checkout?plan=plus&billing=monthly&token={token}{utm_base}&utm_content=subscription_plus"
    contribution_url = f"{FRONTEND_URL}/checkout?type=contribution&amount={contribution_amount}&token={token}{utm_base}&utm_content=contribution_{contribution_amount}"
    pricing_url = f"{FRONTEND_URL}/pricing?utm_source=email_campaign&utm_medium=email&utm_campaign=founding_member&utm_content=pricing_explore"

    print(f"\n[USER] {user.email} (Name: {user.display_name or 'N/A'})")
    print(f"  Checkout Link (Plus Plan): {checkout_url}")
    print(f"  Contribution Link (₹{contribution_amount}): {contribution_url}")
    print(f"  Pricing Link:              {pricing_url}")

    if dry_run:
        print("  [DRY RUN] Email not sent.")
        return True

    # 3. Compile email body
    html_body = build_campaign_html(
        display_name=user.display_name or "",
        checkout_url=checkout_url,
        pricing_url=pricing_url,
        contribution_url=contribution_url,
        contribution_amount=contribution_amount,
        token=token
    )

    # 4. Dispatch email
    try:
        if HAS_FASTAPI_MAIL and conf is not None:
            message = MessageSchema(
                subject="Exclusive Invitation: Join RelayPost Plus or Support our Mission",
                recipients=[user.email],
                body=html_body,
                subtype=MessageType.html
            )
            fm = FastMail(conf)
            await fm.send_message(message)
        else:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "Exclusive Invitation: Join RelayPost Plus or Support our Mission"
            msg["From"] = f"{Envs.MAIL_FROM_NAME} <{Envs.MAIL_FROM}>"
            msg["To"] = user.email
            msg.attach(MIMEText(html_body, "html"))

            if Envs.MAIL_SSL_TLS:
                server = smtplib.SMTP_SSL(Envs.MAIL_SERVER, Envs.MAIL_PORT)
            else:
                server = smtplib.SMTP(Envs.MAIL_SERVER, Envs.MAIL_PORT)
                if Envs.MAIL_STARTTLS:
                    server.starttls()

            if Envs.MAIL_USERNAME and Envs.MAIL_PASSWORD:
                server.login(Envs.MAIL_USERNAME, Envs.MAIL_PASSWORD)
            server.sendmail(Envs.MAIL_FROM, [user.email], msg.as_string())
            server.quit()

        print(f"  [SUCCESS] Email successfully delivered to {user.email}")
        return True
    except Exception as e:
        print(f"  [ERROR] Failed to send email to {user.email}: {e}")
        return False

async def main():
    parser = argparse.ArgumentParser(description="Send RelayPost Plus Founding Member & Supporter campaign email.")
    parser.add_argument("--email", type=str, help="Target a specific email address (e.g. for testing).")
    parser.add_argument("--all", action="store_true", help="Send to all eligible free-tier users.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of emails to send.")
    parser.add_argument("--contribution-amount", type=int, default=50, help="Default one-time contribution amount in INR (default: 50).")
    parser.add_argument("--dry-run", action="store_true", help="Preview links and recipients without sending emails.")
    parser.add_argument("--stats", action="store_true", help="Display tracking statistics of campaign link clicks.")

    args = parser.parse_args()

    db: Session = SessionLocal()
    try:
        # If --stats is requested, show click statistics and exit
        if args.stats:
            stats = crud.get_campaign_stats(db, campaign_name="founding_member")
            print("\n========================================================")
            print("      RELAYPOST CAMPAIGN LINK CLICK TRACKING REPORT     ")
            print("========================================================")
            print(f"Campaign:             {stats['campaign_name']}")
            print(f"Total Link Clicks:    {stats['total_clicks']}")
            print(f"Unique Users Clicked: {stats['unique_users_clicked']}")
            print("\n--- Clicks by Desired Link ---")
            if stats['clicks_by_link']:
                for link_type, count in stats['clicks_by_link'].items():
                    print(f"  • {link_type:<28} : {count} click(s)")
            else:
                print("  (No clicks recorded yet)")

            if stats['recent_clicks']:
                print("\n--- Recent Clicks Log (Latest 25) ---")
                for r in stats['recent_clicks']:
                    email_display = r['email'] or (r['user_id'][:8] if r['user_id'] else 'Anonymous')
                    amt_display = f" (₹{r['amount']})" if r.get('amount') else ""
                    clicked_time = r['clicked_at'][:19].replace('T', ' ') if r.get('clicked_at') else 'N/A'
                    print(f"  [{clicked_time}] {email_display:<26} -> {r['link_type']}{amt_display}")
            print("========================================================\n")
            return

        if not args.email and not args.all and not args.dry_run:
            print("Usage error: Please specify --email <address>, --all, --dry-run, or --stats.")
            print("Example for testing: python send_subscription_campaign.py --email admin@relaypost.me --dry-run")
            print("Example to view click stats: python send_subscription_campaign.py --stats")
            sys.exit(1)

        users = get_eligible_users(db, target_email=args.email, limit=args.limit)
        print(f"Found {len(users)} eligible user(s) for the campaign.")

        if not users:
            print("No users found matching criteria.")
            return

        success_count = 0
        for user in users:
            ok = await send_campaign_to_user(user, contribution_amount=args.contribution_amount, dry_run=args.dry_run)
            if ok:
                success_count += 1
            # Brief pause to respect SMTP rate limits
            if not args.dry_run:
                await asyncio.sleep(0.5)

        print(f"\nFinished campaign: {success_count}/{len(users)} processed successfully.")

    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main())
