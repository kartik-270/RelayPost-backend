import os
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from pydantic import EmailStr
from typing import List

# SMTP Configuration from Environment
class Envs:
    MAIL_USERNAME = os.getenv("SMTP_USERNAME", "no-reply@relaypost.com")
    MAIL_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    MAIL_FROM = os.getenv("SMTP_USERNAME", "no-reply@relaypost.com")
    MAIL_PORT = int(os.getenv("SMTP_PORT", "587"))
    MAIL_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    MAIL_FROM_NAME = "RelayPost Intelligence"
    FRONTEND_URL = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")[0]

conf = ConnectionConfig(
    MAIL_USERNAME=Envs.MAIL_USERNAME,
    MAIL_PASSWORD=Envs.MAIL_PASSWORD,
    MAIL_FROM=Envs.MAIL_FROM,
    MAIL_PORT=Envs.MAIL_PORT,
    MAIL_SERVER=Envs.MAIL_SERVER,
    MAIL_FROM_NAME=Envs.MAIL_FROM_NAME,
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

async def send_invite_email(email: str, token: str):
    invite_url = f"{Envs.FRONTEND_URL}/auth/invite/{token}"
    
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; rounded-xl: 16px;">
        <h2 style="color: #4f46e5;">Welcome to RelayPost Intelligence</h2>
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
        subject="Invitation to join RelayPost Intelligence",
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
