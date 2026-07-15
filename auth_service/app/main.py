import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, status, Response, Request, BackgroundTasks
from typing import List, Optional
import uuid
import hmac
import hashlib
import razorpay
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import google.auth.transport.requests
from google.oauth2 import id_token
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
import os
from datetime import timedelta

from app.crud import crud
from app.models import models
from app.schemas import schemas
from app.core import mail_utils
from app.crud import subscription_crud as sub_crud
from app.core.auth_deps import get_current_active_user, get_password_hash, verify_password, create_access_token, get_current_user, require_role
from app.core.database import engine, get_db
from app.services.subscription_scheduler import subscription_scheduler

app = FastAPI(title="Auth Microservice")

# --- EXCEPTION HANDLERS ---
@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request, exc: IntegrityError):
    msg = str(exc.orig).lower()
    detail = "An item with this value already exists."
    
    if "unique constraint" in msg or "already exists" in msg:
        if "users_email_key" in msg: detail = "This email is already registered."
        
        return Response(content='{"detail": "' + detail + '"}', status_code=409, media_type="application/json")
    
    return Response(content='{"detail": "Database integrity error."}', status_code=400, media_type="application/json")

raw_origins = os.environ.get("CORS_ORIGINS", "")
if raw_origins:
    cors_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
else:
    cors_origins = []

if not cors_origins:
    cors_origins = ["https://relaypost.me"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auto creating DB for simplicity if not using alembic in local test
try:
    models.Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Startup Warning: Database table creation failed (expected if DB is still starting): {e}")

@app.on_event("startup")
async def startup_event():
    subscription_scheduler.start()
    print("Subscription scheduler started.")

@app.on_event("shutdown")
async def shutdown_event():
    subscription_scheduler.shutdown(wait=False)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "your-google-client-id")

class GoogleAuthRequest(BaseModel):
    token: str
    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    timezone: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None

def get_location_from_ip(ip: str):
    default_loc = {
        "country": "N/A",
        "state": "N/A",
        "city": "Unknown",
        "timezone": "UTC",
        "latitude": "0.0",
        "longitude": "0.0"
    }
    if not ip or ip == "127.0.0.1" or ip == "::1":
        return default_loc
    try:
        import requests
        resp = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                return {
                    "country": data.get("country") or "N/A",
                    "state": data.get("regionName") or "N/A",
                    "city": data.get("city") or "Unknown",
                    "timezone": data.get("timezone") or "UTC",
                    "latitude": str(data.get("lat")) if data.get("lat") else "0.0",
                    "longitude": str(data.get("lon")) if data.get("lon") else "0.0"
                }
    except Exception:
        pass
    return default_loc

@app.post("/auth/register", response_model=schemas.UserResponse, status_code=201)
async def register(request: Request, user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    if not user.country:
        client_ip = request.headers.get("X-Forwarded-For")
        if not client_ip:
            client_ip = request.client.host
        else:
            client_ip = client_ip.split(",")[0].strip()
            
        loc = get_location_from_ip(client_ip)
        if loc:
            user.country = loc.get("country")
            user.state = loc.get("state")
            user.city = loc.get("city")
            user.timezone = loc.get("timezone")
            user.latitude = loc.get("latitude")
            user.longitude = loc.get("longitude")

    hashed_password = get_password_hash(user.password) if user.password else None
    new_user = crud.create_user(db=db, user=user, hashed_password=hashed_password)
    
    # Send verification email if not google auth
    if not new_user.is_verified and new_user.verification_token:
        await mail_utils.send_verification_email(new_user.email, new_user.verification_token)
        
    return new_user

@app.post("/auth/token", response_model=schemas.Token)
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, email=form_data.username)
    if not user or not user.hashed_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    
    if not user.is_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="NOT_VERIFIED")

    # Update location for existing users if missing
    if not user.country:
        client_ip = request.headers.get("X-Forwarded-For")
        if not client_ip:
            client_ip = request.client.host
        else:
            client_ip = client_ip.split(",")[0].strip()
            
        loc = get_location_from_ip(client_ip)
        if loc:
            user.country = loc.get("country")
            user.state = loc.get("state")
            user.city = loc.get("city")
            user.timezone = loc.get("timezone")
            user.latitude = loc.get("latitude")
            user.longitude = loc.get("longitude")
            db.commit()

    
    access_token_expires = timedelta(minutes=60*24)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value, "display_name": user.display_name}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/auth/verify", response_model=schemas.Token)
def verify_email(payload: schemas.VerifyRequest, db: Session = Depends(get_db)):
    user = crud.get_user_by_verification_token(db, payload.token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    
    verified_user = crud.verify_user(db, user.id)
    
    access_token_expires = timedelta(minutes=60*24)
    access_token = create_access_token(
        data={"sub": str(verified_user.id), "email": verified_user.email, "role": verified_user.role.value, "display_name": verified_user.display_name}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

class ResendRequest(BaseModel):
    email: str

@app.post("/auth/resend-verification")
async def resend_verification(payload: ResendRequest, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, email=payload.email)
    if not user:
        # Don't reveal if user exists
        return {"msg": "If an unverified account exists, an email was sent"}
    
    if user.is_verified:
        return {"msg": "Account is already verified"}
        
    if not user.verification_token:
        # Generate new token if it doesn't exist
        user.verification_token = str(uuid.uuid4())
        db.commit()
        
    await mail_utils.send_verification_email(user.email, user.verification_token)
    return {"msg": "Verification email sent"}

@app.post("/auth/forgot-password/request")
async def request_password_reset(request: schemas.ForgotPasswordRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, email=request.email)
    if not user or user.is_deleted:
        # Always return success to prevent email enumeration
        return {"msg": "If that email is registered, an OTP has been sent."}
    
    import random
    from datetime import datetime, timezone, timedelta
    from app.core import auth_deps
    
    # Generate 6 digit OTP
    otp = f"{random.randint(0, 999999):06d}"
    
    # Hash and save
    user.reset_otp_hash = auth_deps.get_password_hash(otp)
    user.reset_otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.commit()
    
    # Send email in background
    background_tasks.add_task(mail_utils.send_password_reset_otp_email, user.email, otp)
    
    return {"msg": "If that email is registered, an OTP has been sent."}

@app.post("/auth/forgot-password/reset")
def reset_password(request: schemas.ForgotPasswordReset, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, email=request.email)
    if not user or user.is_deleted:
        raise HTTPException(status_code=400, detail="Invalid request")
        
    from datetime import datetime, timezone
    
    if not user.reset_otp_hash or not user.reset_otp_expires_at:
        raise HTTPException(status_code=400, detail="No active reset request found")
        
    if datetime.now(timezone.utc) > user.reset_otp_expires_at:
        raise HTTPException(status_code=400, detail="OTP has expired")
        
    if not verify_password(request.otp, user.reset_otp_hash):
        raise HTTPException(status_code=400, detail="Invalid OTP")
        
    # Success! Update password
    user.hashed_password = get_password_hash(request.new_password)
    user.reset_otp_hash = None
    user.reset_otp_expires_at = None
    db.commit()
    
    return {"msg": "Password has been successfully reset"}

@app.post("/auth/google")
def google_auth(fastapi_req: Request, request: GoogleAuthRequest, db: Session = Depends(get_db)):
    try:
        idinfo = id_token.verify_oauth2_token(
            request.token, 
            google.auth.transport.requests.Request(), 
            GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=10
        )
        email = idinfo['email']
        google_id = idinfo['sub']
        name = idinfo.get('name')
        picture = idinfo.get('picture')
        
        is_new = False
        user = crud.get_user_by_email(db, email=email)
        if not user:
            loc = {}
            if not request.country:
                client_ip = fastapi_req.headers.get("X-Forwarded-For")
                if not client_ip:
                    client_ip = fastapi_req.client.host
                else:
                    client_ip = client_ip.split(",")[0].strip()
                loc = get_location_from_ip(client_ip)
            
            # Register new user from google
            user_create = schemas.UserCreate(
                email=email, 
                display_name=name, 
                avatar=picture, 
                google_id=google_id,
                country=request.country or loc.get("country"),
                state=request.state or loc.get("state"),
                city=request.city or loc.get("city"),
                timezone=request.timezone or loc.get("timezone"),
                latitude=request.latitude or loc.get("latitude"),
                longitude=request.longitude or loc.get("longitude")
            )
            user = crud.create_user(db=db, user=user_create, google_id=google_id)
            is_new = True
        else:
            # If location is missing for existing user, try to get it
            if not user.country:
                client_ip = fastapi_req.headers.get("X-Forwarded-For")
                if not client_ip:
                    client_ip = fastapi_req.client.host
                else:
                    client_ip = client_ip.split(",")[0].strip()
                loc = get_location_from_ip(client_ip)
                if loc:
                    user.country = loc.get("country")
                    user.state = loc.get("state")
                    user.city = loc.get("city")
                    user.timezone = loc.get("timezone")
                    user.latitude = loc.get("latitude")
                    user.longitude = loc.get("longitude")
                    db.commit()
            
        access_token = create_access_token(
            data={"sub": str(user.id), "email": user.email, "role": user.role.value, "display_name": user.display_name}, expires_delta=timedelta(minutes=60*24)
        )
        return {"access_token": access_token, "token_type": "bearer", "is_new_user": is_new}
    except ValueError as e:
        print(f"Token verification failed: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Google token: {str(e)}")

@app.get("/")
def read_root():
    return {"status": "online", "service": "RelayPost Auth Service", "version": "1.0.0"}

@app.get("/users/me", response_model=schemas.UserResponse)
async def read_users_me(current_user: models.User = Depends(get_current_active_user)):
    return current_user

@app.put("/users/me/password")
def change_password(payload: schemas.ChangePasswordRequest, current_user: models.User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not current_user.hashed_password:
        raise HTTPException(status_code=400, detail="Cannot change password for users registered via OAuth.")
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    
    current_user.hashed_password = get_password_hash(payload.new_password)
    db.commit()
    return {"message": "Password updated successfully"}

@app.get("/admin/users", response_model=List[schemas.UserResponse])
def list_users(skip: int = 0, limit: int = 100, role: models.RoleEnum = None, current_user: models.User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if current_user.role != models.RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return crud.get_users(db, skip=skip, limit=limit, role=role)

@app.put("/admin/users/{user_id}", response_model=schemas.UserResponse)
def update_user_admin(user_id: str, updates: schemas.UserUpdate, current_user: models.User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if current_user.role != models.RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    updated_user = crud.update_user(db, user_id, updates)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    return updated_user

@app.delete("/admin/users/{user_id}")
def delete_user(user_id: str, current_user: models.User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if current_user.role != models.RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    user_to_delete = crud.get_user(db, user_id=user_id)
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_to_delete.is_deleted = True
    user_to_delete.is_active = False
    db.commit()
    return {"message": "User deleted successfully"}

# --- INVITATION ROUTES ---

@app.post("/admin/invites", response_model=schemas.InviteResponse)
async def create_invitation(invite: schemas.InviteCreate, current_user: models.User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if current_user.role != models.RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can invite members")
    
    db_invite = crud.create_invite(db, email=invite.email, role=invite.role)
    # Send email
    await mail_utils.send_invite_email(invite.email, db_invite.token)
    
    return db_invite

@app.get("/auth/invite/{token}", response_model=schemas.InviteResponse)
def get_invite_details(token: str, db: Session = Depends(get_db)):
    db_invite = crud.get_invite_by_token(db, token)
    if not db_invite:
        raise HTTPException(status_code=404, detail="Invalid or expired invitation")
    return db_invite

@app.post("/auth/invite/register", response_model=schemas.UserResponse)
def register_by_invite(payload: schemas.InviteSignup, db: Session = Depends(get_db)):
    db_invite = crud.get_invite_by_token(db, payload.token)
    if not db_invite:
        raise HTTPException(status_code=404, detail="Invalid or expired invitation")
    
    # Check if email is already taken
    existing_user = crud.get_user_by_email(db, email=db_invite.email)
    if existing_user:
        crud.mark_invite_used(db, db_invite.id)
        raise HTTPException(status_code=400, detail="User already registered")

    # Create User
    hashed_password = get_password_hash(payload.password)
    user_create = schemas.UserCreate(
        email=db_invite.email, 
        password=payload.password, 
        display_name=payload.display_name or db_invite.email.split('@')[0],
        role=db_invite.role
    )
    user = crud.create_user(db=db, user=user_create, hashed_password=hashed_password)
    
    # Mark invite as used
    crud.mark_invite_used(db, db_invite.id)
    
    return user

# --- STATS ROUTES ---

@app.get("/admin/stats/auth", response_model=schemas.AuthStats)
def get_auth_statistics(current_user: models.User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if current_user.role != models.RoleEnum.ADMIN:
        raise HTTPException(status_code=403, detail="Access denied")
    return crud.get_auth_stats(db)

# --- PAYMENT ROUTES ---
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET")

if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    rzp_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
else:
    rzp_client = None

@app.post("/auth/payment/create-order", response_model=schemas.CreateOrderResponse)
def create_payment_order(payload: schemas.CreateOrderRequest, current_user: models.User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    if not rzp_client:
        raise HTTPException(status_code=500, detail="Razorpay is not configured")
    
    amount = payload.amount
    if not (100 <= amount <= 5000000):
        raise HTTPException(status_code=400, detail="Amount must be between 100 and 5000000 paise")

    try:
        order_data = {
            "amount": amount,
            "currency": "INR",
            "receipt": f"rcpt_{str(current_user.id)[:8]}_{str(uuid.uuid4())[:8]}",
            "payment_capture": 1
        }
        order = rzp_client.order.create(data=order_data)
        
        crud.create_contribution(db, current_user.id, amount, "INR", order["id"])
        
        return {
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/payment/verify", response_model=schemas.VerifyPaymentResponse)
def verify_payment(payload: schemas.VerifyPaymentRequest, current_user: models.User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    db_contribution = crud.get_contribution_by_order_id(db, payload.razorpay_order_id)
    if not db_contribution:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if db_contribution.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your order")

    # Verify signature
    msg = f"{payload.razorpay_order_id}|{payload.razorpay_payment_id}"
    generated_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode('utf-8'),
        msg.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    if generated_signature != payload.razorpay_signature:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Double check amount from razorpay
    try:
        rzp_order = rzp_client.order.fetch(payload.razorpay_order_id)
        if rzp_order["amount"] != db_contribution.amount:
            raise HTTPException(status_code=400, detail="Amount mismatch detected")
            
        crud.update_contribution_status(db, db_contribution, "SUCCESS", payload.razorpay_payment_id)
        return {"status": "SUCCESS", "message": "Payment verified successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/payment/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")
    
    if not signature or not RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(status_code=400, detail="Missing signature or webhook secret")

    try:
        rzp_client.utility.verify_webhook_signature(body.decode('utf-8'), signature, RAZORPAY_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event")

    if event in ["payment.captured", "payment.failed"]:
        payment = payload["payload"]["payment"]["entity"]
        order_id = payment.get("order_id")
        payment_id = payment.get("id")
        status = "SUCCESS" if event == "payment.captured" else "FAILED"
        
        db_contribution = crud.get_contribution_by_order_id(db, order_id)
        if db_contribution:
            # Idempotency: only update if not already SUCCESS
            if db_contribution.status != "SUCCESS" or status == "SUCCESS":
                crud.update_contribution_status(db, db_contribution, status, payment_id)

    return {"status": "ok"}


# =============================================================================
# SUBSCRIPTION ROUTES
# =============================================================================

RAZORPAY_PLANS = {
    # plan_id values will come from your Razorpay dashboard
    ("plus",  "monthly"): os.environ.get("RZP_PLAN_PLUS_MONTHLY", ""),
    ("plus",  "annual"):  os.environ.get("RZP_PLAN_PLUS_ANNUAL", ""),
    ("pro",   "monthly"): os.environ.get("RZP_PLAN_PRO_MONTHLY", ""),
    ("pro",   "annual"):  os.environ.get("RZP_PLAN_PRO_ANNUAL", ""),
}


@app.get("/subscription/status", response_model=schemas.SubscriptionResponse)
def get_subscription_status(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get current user's subscription details."""
    sub = sub_crud.get_or_create_free_subscription(db, current_user.id)
    return sub


@app.get("/subscription/tier", response_model=schemas.TierStatusResponse)
def get_tier_status(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Lightweight tier check — used by other services internally."""
    return sub_crud.get_tier_status(db, current_user.id)


@app.get("/internal/tier/{user_id}", response_model=schemas.TierStatusResponse)
def get_tier_status_internal(user_id: str, db: Session = Depends(get_db)):
    """
    Internal endpoint — called by content_service and tracking_service
    via docker internal network only. Not exposed externally.
    """
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id")
    return sub_crud.get_tier_status(db, uid)


@app.post("/subscription/create-razorpay", response_model=schemas.RazorpaySubscriptionResponse)
def create_razorpay_subscription(
    payload: schemas.CreateRazorpaySubscriptionRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Step 1: Create Razorpay subscription object and return it to the frontend.
    Frontend then shows Razorpay checkout modal with mandate capture.
    """
    if not rzp_client:
        raise HTTPException(status_code=500, detail="Razorpay not configured")

    tier_val = payload.tier.value
    interval_val = payload.billing_interval.value
    plan_id = RAZORPAY_PLANS.get((tier_val, interval_val), "")
    if not plan_id:
        raise HTTPException(status_code=400, detail=f"No Razorpay plan configured for {tier_val}/{interval_val}")

    amount = sub_crud.TIER_PRICES_PAISE.get((tier_val, interval_val), 0)

    # Check if they already have an active subscription for upgrade
    existing_sub = sub_crud.get_subscription(db, current_user.id)
    existing_sub = sub_crud.get_subscription(db, current_user.id)
    old_rzp_id = existing_sub.razorpay_subscription_id if existing_sub else None

    # If they are upgrading an active, non-cancelling subscription
    is_upgrade = False
    if existing_sub:
        is_upgrade = tier_val != existing_sub.tier.value or interval_val != existing_sub.billing_interval.value
        
    if old_rzp_id and existing_sub.status in ["active", "trialing", "past_due", "paused"] and not existing_sub.cancel_at_period_end and is_upgrade:
        # Verify with Razorpay that it's actually upgradable to self-heal any out-of-sync states
        import requests
        import json
        try:
            auth = (rzp_client.auth[0], rzp_client.auth[1])
            check_res = requests.get(f"https://api.razorpay.com/v1/subscriptions/{old_rzp_id}", auth=auth)
            if check_res.ok:
                sub_data = check_res.json()
                rzp_status = sub_data.get("status")
                
                # Razorpay explicitly blocks upgrading UPI mandates
                # We do a safe search for UPI payment methods in the raw JSON
                sub_data_str = json.dumps(sub_data).lower().replace(" ", "")
                is_upi = '"payment_method":"upi"' in sub_data_str or '"method":"upi"' in sub_data_str

                if rzp_status in ["active", "authenticated"] and not is_upi:
                    return {
                        "razorpay_subscription_id": old_rzp_id,
                        "razorpay_key_id": RAZORPAY_KEY_ID or "",
                        "tier": tier_val,
                        "amount_paise": amount,
                        "currency": "INR",
                        "trial_end": None,
                        "is_upgrade_eligible": True,
                    }
                else:
                    print(f"DEBUG: Local DB active but Razorpay says {rzp_status} or is_upi={is_upi}. Falling back to new subscription.")
        except Exception as e:
            print(f"DEBUG: Failed to verify Razorpay status: {e}")
            
        # If we reach here, it's not upgradable. Fall through and create a new one.
        is_fallback_upgrade = True
    else:
        is_fallback_upgrade = False

    try:
        do_trial = existing_sub is None or not existing_sub.has_used_trial
        
        from datetime import datetime, timezone, timedelta
        sub_payload = {
            "plan_id": plan_id,
            "total_count": 12 if interval_val == "monthly" else 1,
            "quantity": 1,
            "customer_notify": 1,
        }
        
        if do_trial:
            start_at = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
            sub_payload["start_at"] = start_at
            
        rzp_sub = rzp_client.subscription.create(sub_payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Razorpay error: {str(e)}")

    trial_end = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat() if do_trial else None

    return {
        "razorpay_subscription_id": rzp_sub["id"],
        "razorpay_key_id": RAZORPAY_KEY_ID or "",
        "tier": tier_val,
        "amount_paise": amount,
        "currency": "INR",
        "trial_end": trial_end,
        "is_fallback_upgrade": is_fallback_upgrade,
    }


@app.post("/subscription/activate", response_model=schemas.SubscriptionResponse)
def activate_subscription(
    payload: schemas.CreateRazorpaySubscriptionRequest,
    razorpay_subscription_id: str,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Step 2: Called after user completes Razorpay checkout.
    Creates/updates the local subscription record.
    """
    tier_val = payload.tier.value
    interval_val = payload.billing_interval.value
    plan_id = RAZORPAY_PLANS.get((tier_val, interval_val), "")

    existing_sub = sub_crud.get_subscription(db, current_user.id)
    old_rzp_id = existing_sub.razorpay_subscription_id if existing_sub else None

    # IMPORTANT: If they upgraded via fallback (created a new subscription ID),
    # we MUST cancel the old mandate on Razorpay to prevent double-billing!
    if old_rzp_id and old_rzp_id != razorpay_subscription_id:
        if rzp_client and existing_sub.status in ["active", "trialing", "past_due", "paused"]:
            try:
                # Issue an immediate cancellation of the old mandate
                rzp_client.subscription.cancel(old_rzp_id, {"cancel_at_cycle_end": 0})
                print(f"DEBUG: Successfully cancelled old mandate {old_rzp_id} after fallback upgrade.")
            except Exception as e:
                print(f"DEBUG: Failed to cancel old mandate {old_rzp_id}: {e}")

    sub = sub_crud.create_subscription(
        db=db,
        user_id=current_user.id,
        tier=payload.tier,
        billing_interval=payload.billing_interval,
        razorpay_subscription_id=razorpay_subscription_id,
        razorpay_plan_id=plan_id,
        with_trial=True,
    )
    return sub

@app.post("/subscription/upgrade", response_model=schemas.SubscriptionResponse)
def upgrade_subscription(
    payload: schemas.CreateRazorpaySubscriptionRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Step 2 (Native Upgrade): Updates the user's existing Razorpay subscription with the new plan.
    Proration is automatically handled by Razorpay.
    """
    if not rzp_client:
        raise HTTPException(status_code=500, detail="Razorpay not configured")

    existing_sub = sub_crud.get_subscription(db, current_user.id)
    if not existing_sub or not existing_sub.razorpay_subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription found to upgrade.")

    tier_val = payload.tier.value
    interval_val = payload.billing_interval.value
    plan_id = RAZORPAY_PLANS.get((tier_val, interval_val), "")
    
    if not plan_id:
        raise HTTPException(status_code=400, detail="Invalid plan for upgrade.")

    import requests
    try:
        auth = (rzp_client.auth[0], rzp_client.auth[1])
        
        # Debug: Fetch the subscription to see its actual state
        get_res = requests.get(
            f"https://api.razorpay.com/v1/subscriptions/{existing_sub.razorpay_subscription_id}",
            auth=auth
        )
        if get_res.ok:
            sub_data = get_res.json()
            print(f"DEBUG UPGRADE: Subscription {sub_data['id']} is in state: {sub_data['status']}")
            
            # If it's not active or authenticated, we CANNOT do a native upgrade.
            if sub_data['status'] not in ['active', 'authenticated']:
                raise HTTPException(status_code=400, detail="Cannot upgrade this subscription because its underlying payment mandate is no longer active. Please cancel it and start a new plan.")

        res = requests.patch(
            f"https://api.razorpay.com/v1/subscriptions/{existing_sub.razorpay_subscription_id}",
            json={"plan_id": plan_id, "customer_notify": 1},
            auth=auth
        )
        if not res.ok:
            raise Exception(res.text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update subscription in Razorpay: {e}")

    # Update local DB to reflect the new plan
    sub = sub_crud.create_subscription(
        db=db,
        user_id=current_user.id,
        tier=payload.tier,
        billing_interval=payload.billing_interval,
        razorpay_subscription_id=existing_sub.razorpay_subscription_id,
        razorpay_plan_id=plan_id,
        with_trial=False,  # No trial on upgrade
    )
    
    return sub


@app.post("/subscription/cancel")
async def cancel_subscription(
    payload: schemas.SubscriptionCancelRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Cancel autopay — user stays on current plan until period end."""
    sub = sub_crud.cancel_at_period_end(db, current_user.id, payload.reason)
    if not sub:
        raise HTTPException(status_code=400, detail="No active paid subscription found")

    # Cancel on Razorpay side too
    if sub.razorpay_subscription_id and rzp_client:
        try:
            rzp_client.subscription.cancel(sub.razorpay_subscription_id, {"cancel_at_cycle_end": 1})
        except Exception as e:
            print(f"Razorpay cancel_at_cycle_end failed: {e}. Trying immediate cancel...")
            try:
                rzp_client.subscription.cancel(sub.razorpay_subscription_id, {"cancel_at_cycle_end": 0})
            except Exception as e2:
                print(f"Razorpay immediate cancel warning: {e2}")

    end_date = sub.current_period_end.strftime("%b %d, %Y") if sub.current_period_end else "period end"
    await mail_utils.send_subscription_cancelled_email(current_user.email, sub.tier.value, end_date)
    sub_crud.create_user_notification(
        db, current_user.id,
        "autopay_cancelled",
        "Autopay turned off",
        f"Your {sub.tier.value.title()} plan remains active until {end_date}.",
        action_url="/subscription",
    )
    return {"message": "Subscription will cancel at period end", "ends_at": sub.current_period_end}


@app.post("/subscription/reactivate", response_model=schemas.SubscriptionResponse)
def reactivate_subscription(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Re-enable autopay before period end."""
    sub = sub_crud.reactivate_subscription(db, current_user.id)
    if not sub:
        raise HTTPException(status_code=400, detail="No cancellable subscription found")

    if sub.razorpay_subscription_id and rzp_client:
        raise HTTPException(
            status_code=400,
            detail="To reactivate your plan, please select a new plan from the pricing page. Previous payment mandates cannot be reactivated once cancelled."
        )

    return sub


@app.post("/payment/subscription/webhook")
async def razorpay_subscription_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Razorpay subscription lifecycle webhooks."""
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    if not signature or not RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(status_code=400, detail="Missing signature")

    try:
        rzp_client.utility.verify_webhook_signature(
            body.decode("utf-8"), signature, RAZORPAY_WEBHOOK_SECRET
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event", "")
    entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})
    rzp_sub_id = entity.get("id")

    if not rzp_sub_id:
        return {"status": "ignored"}

    if event == "subscription.charged":
        sub = sub_crud.on_payment_success(db, rzp_sub_id)
        if sub:
            next_date = sub.current_period_end.strftime("%b %d, %Y") if sub.current_period_end else ""
            await mail_utils.send_payment_success_email(
                sub.user.email, sub.tier.value, next_date, sub.amount_paise or 0
            )
            sub_crud.create_user_notification(
                db, sub.user_id, "payment_success",
                "Payment successful",
                f"Your {sub.tier.value.title()} subscription has been renewed.",
                action_url="/subscription",
            )

    elif event == "subscription.pending":
        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        sub = sub_crud.on_payment_failed(db, rzp_sub_id)
        if sub:
            grace_str = sub.grace_period_end.strftime("%b %d, %Y") if sub.grace_period_end else ""
            await mail_utils.send_payment_failed_email(
                sub.user.email, sub.tier.value, sub.payment_retry_count, grace_str
            )
            sub_crud.create_user_notification(
                db, sub.user_id, "payment_failed",
                "Payment failed",
                f"We couldn't charge your card. Grace period ends {grace_str}. Update your payment method.",
                action_url="/subscription",
            )

    elif event == "subscription.halted":
        sub = sub_crud.on_subscription_halted(db, rzp_sub_id)
        if sub:
            await mail_utils.send_subscription_expired_email(sub.user.email, sub.tier.value, "payment_failed")
            sub_crud.create_user_notification(
                db, sub.user_id, "subscription_expired",
                "Plan downgraded to Free",
                "All payment retries failed. You've been moved to the Free plan.",
                action_url="/pricing",
            )

    elif event == "subscription.cancelled":
        sub_crud.on_subscription_cancelled(db, rzp_sub_id)

    return {"status": "ok"}


# =============================================================================
# USER NOTIFICATION ROUTES
# =============================================================================

@app.get("/notifications", response_model=List[schemas.UserNotificationResponse])
def get_notifications(
    limit: int = 20,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return sub_crud.get_user_notifications(db, current_user.id, limit=limit)


@app.get("/notifications/unread-count")
def get_unread_count(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return {"count": sub_crud.get_unread_count(db, current_user.id)}


@app.post("/notifications/{notif_id}/read")
def mark_notification_read(
    notif_id: uuid.UUID,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    success = sub_crud.mark_notification_read(db, notif_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"message": "Marked as read"}


@app.post("/notifications/read-all")
def mark_all_read(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    sub_crud.mark_all_notifications_read(db, current_user.id)
    return {"message": "All notifications marked as read"}


# =============================================================================
# ADMIN ROUTES
# =============================================================================

class AdminUserResponse(schemas.UserResponse):
    tier: str
    subscription_status: str

@app.get("/admin/users", response_model=List[AdminUserResponse])
def get_all_users_admin(
    skip: int = 0, limit: int = 100,
    current_user: models.User = Depends(require_role(models.RoleEnum.ADMIN)),
    db: Session = Depends(get_db),
):
    """Admin route to list all users with their current tier status."""
    users = crud.get_users(db, skip=skip, limit=limit)
    response = []
    for u in users:
        tier_data = sub_crud.get_tier_status(db, u.id)
        user_dict = schemas.UserResponse.model_validate(u).model_dump()
        user_dict["tier"] = tier_data.tier
        user_dict["subscription_status"] = tier_data.status
        response.append(user_dict)
    return response

@app.put("/admin/users/{user_id}/subscription", response_model=schemas.SubscriptionResponse)
def override_user_subscription(
    user_id: str,
    payload: schemas.SubscriptionOverrideRequest,
    current_user: models.User = Depends(require_role(models.RoleEnum.ADMIN)),
    db: Session = Depends(get_db),
):
    """Admin route to override a user's subscription tier for testing purposes."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    
    user = crud.get_user(db, uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    sub = sub_crud.get_or_create_free_subscription(db, uid)
    
    sub.tier = payload.tier
    sub.status = models.SubscriptionStatus.ACTIVE
    
    # Reset some fields so the tier works cleanly without Razorpay interference for now
    sub.is_trial = False
    sub.cancel_at_period_end = False
    sub.payment_failed_at = None
    sub.grace_period_end = None
    
    # Extend period for a month for testing purposes
    from datetime import datetime, timezone, timedelta
    sub.current_period_start = datetime.now(timezone.utc)
    sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=30)
    
    db.commit()
    db.refresh(sub)
    return sub



INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "relaypost-internal")

from fastapi import Header

def _verify_internal(x_internal_secret: Optional[str] = Header(None)):
    if not x_internal_secret or x_internal_secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Invalid internal secret")


@app.get("/internal/users/digest-recipients")
def get_digest_recipients(
    db: Session = Depends(get_db),
    _: None = Depends(_verify_internal),
):
    """
    Returns all active, non-deleted users for digest email dispatch.
    Called internally by content_service digest scheduler.
    """
    users = (
        db.query(models.User)
        .filter(
            models.User.is_active == True,
            models.User.is_deleted == False,
        )
        .all()
    )
    return [
        {
            "user_id":      str(u.id),
            "email":        u.email,
            "display_name": u.display_name or u.email.split("@")[0],
        }
        for u in users
    ]


class DigestEmailPayload(BaseModel):
    email: str
    display_name: str
    digest: dict
    opt_out_url: str
    frontend_url: str


@app.post("/internal/send-digest-email")
async def send_digest_email_internal(
    payload: DigestEmailPayload,
    _: None = Depends(_verify_internal),
):
    """
    Sends the weekly digest HTML email to a single user.
    Called internally by content_service digest scheduler.
    """
    from app.core.mail_utils import send_weekly_digest_email
    try:
        ok = await send_weekly_digest_email(
            email=payload.email,
            display_name=payload.display_name,
            digest=payload.digest,
            opt_out_url=payload.opt_out_url,
            frontend_url=payload.frontend_url,
        )
        if ok:
            return {"status": "sent"}
        return {"status": "failed"}
    except Exception as e:
        print(f"[DIGEST EMAIL ERROR] {payload.email}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


