import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, status, Response, Request
from typing import List
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

import crud, models, schemas
import mail_utils
from auth_deps import get_current_active_user, get_password_hash, verify_password, create_access_token, get_current_user
from database import engine, get_db

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
    cors_origins = ["http://localhost:3000", "http://localhost:3001", "http://localhost:3002"]

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

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "your-google-client-id")

class GoogleAuthRequest(BaseModel):
    token: str

@app.post("/auth/register", response_model=schemas.UserResponse, status_code=201)
async def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = get_password_hash(user.password) if user.password else None
    new_user = crud.create_user(db=db, user=user, hashed_password=hashed_password)
    
    # Send verification email if not google auth
    if not new_user.is_verified and new_user.verification_token:
        await mail_utils.send_verification_email(new_user.email, new_user.verification_token)
        
    return new_user

@app.post("/auth/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, email=form_data.username)
    if not user or not user.hashed_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    
    if not user.is_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="NOT_VERIFIED")
    
    access_token_expires = timedelta(minutes=60*24)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}, expires_delta=access_token_expires
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
        data={"sub": str(verified_user.id), "email": verified_user.email, "role": verified_user.role.value}, expires_delta=access_token_expires
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

@app.post("/auth/google")
def google_auth(request: GoogleAuthRequest, db: Session = Depends(get_db)):
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
        
        user = crud.get_user_by_email(db, email=email)
        if not user:
            # Register new user from google
            user_create = schemas.UserCreate(email=email, display_name=name, avatar=picture, google_id=google_id)
            user = crud.create_user(db=db, user=user_create, google_id=google_id)
            
        access_token = create_access_token(
            data={"sub": str(user.id), "email": user.email, "role": user.role.value}, expires_delta=timedelta(minutes=60*24)
        )
        return {"access_token": access_token, "token_type": "bearer"}
    except ValueError as e:
        print(f"Token verification failed: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Google token: {str(e)}")

@app.get("/")
def read_root():
    return {"status": "online", "service": "RelayPost Auth Service", "version": "1.0.0"}

@app.get("/users/me", response_model=schemas.UserResponse)
def read_users_me(current_user: models.User = Depends(get_current_active_user)):
    return current_user

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
