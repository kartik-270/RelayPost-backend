from sqlalchemy.orm import Session
from schemas import UserCreate, UserUpdate
import models
import uuid

def get_user(db: Session, user_id: str):
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: Session, user: UserCreate, hashed_password: str = None, google_id: str = None):
    db_user = models.User(
        email=user.email,
        hashed_password=hashed_password,
        google_id=google_id,
        display_name=user.display_name,
        avatar=user.avatar,
        bio=user.bio,
        specialization=user.specialization,
        role=user.role if user.role else models.RoleEnum.VIEWER
    )
    db.add(db_user)
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
