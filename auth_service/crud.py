from sqlalchemy.orm import Session
from schemas import UserCreate, UserUpdate
import models
import uuid

def get_user(db: Session, user_id: str):
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: Session, user: UserCreate, hashed_password: str = None, google_id: str = None):
    # If Google ID is provided, automatically verify the user
    is_verified = True if google_id else False
    verification_token = None if google_id else str(uuid.uuid4())

    db_user = models.User(
        email=user.email,
        hashed_password=hashed_password,
        google_id=google_id,
        display_name=user.display_name,
        avatar=user.avatar,
        bio=user.bio,
        specialization=user.specialization,
        role=user.role if user.role else models.RoleEnum.VIEWER,
        is_verified=is_verified,
        verification_token=verification_token
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_verification_token(db: Session, token: str):
    return db.query(models.User).filter(models.User.verification_token == token).first()

def verify_user(db: Session, user_id: uuid.UUID):
    db_user = get_user(db, user_id)
    if db_user:
        db_user.is_verified = True
        db_user.verification_token = None
        db.commit()
        db.refresh(db_user)
    return db_user

def get_users(db: Session, skip: int = 0, limit: int = 100, role: models.RoleEnum = None):
    query = db.query(models.User).filter(models.User.is_deleted == False)
    if role:
        query = query.filter(models.User.role == role)
    return query.offset(skip).limit(limit).all()

def update_user(db: Session, user_id: str, updates: UserUpdate):
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    
    update_data = updates.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_user, key, value)
    
    db.commit()
    db.refresh(db_user)
    return db_user

# --- Invites ---
from datetime import datetime, timedelta, timezone

def create_invite(db: Session, email: str, role: models.RoleEnum):
    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
    
    db_invite = models.Invite(
        email=email,
        token=token,
        role=role,
        expires_at=expires_at
    )
    db.add(db_invite)
    db.commit()
    db.refresh(db_invite)
    return db_invite

def get_invite_by_token(db: Session, token: str):
    return db.query(models.Invite).filter(
        models.Invite.token == token,
        models.Invite.is_used == False,
        models.Invite.expires_at > datetime.now(timezone.utc)
    ).first()

def mark_invite_used(db: Session, invite_id: uuid.UUID):
    db_invite = db.query(models.Invite).filter(models.Invite.id == invite_id).first()
    if db_invite:
        db_invite.is_used = True
        db.commit()
    return db_invite

# --- Stats ---
def get_auth_stats(db: Session):
    total = db.query(models.User).filter(models.User.is_deleted == False).count()
    admins = db.query(models.User).filter(models.User.role == models.RoleEnum.ADMIN, models.User.is_deleted == False).count()
    publishers = db.query(models.User).filter(models.User.role == models.RoleEnum.PUBLISHER, models.User.is_deleted == False).count()
    viewers = db.query(models.User).filter(models.User.role == models.RoleEnum.VIEWER, models.User.is_deleted == False).count()
    
    return {
        "total_users": total,
        "admin_count": admins,
        "publisher_count": publishers,
        "viewer_count": viewers
    }

# --- Contributions ---
def create_contribution(db: Session, user_id: uuid.UUID, amount: int, currency: str, razorpay_order_id: str):
    db_contribution = models.Contribution(
        user_id=user_id,
        amount=amount,
        currency=currency,
        razorpay_order_id=razorpay_order_id,
        status="PENDING"
    )
    db.add(db_contribution)
    db.commit()
    db.refresh(db_contribution)
    return db_contribution

def get_contribution_by_order_id(db: Session, razorpay_order_id: str):
    return db.query(models.Contribution).filter(models.Contribution.razorpay_order_id == razorpay_order_id).first()

def update_contribution_status(db: Session, db_contribution: models.Contribution, status: str, razorpay_payment_id: str = None):
    db_contribution.status = status
    if razorpay_payment_id:
        db_contribution.razorpay_payment_id = razorpay_payment_id
    db.commit()
    db.refresh(db_contribution)
    return db_contribution
