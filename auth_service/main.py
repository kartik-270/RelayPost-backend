import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import google.auth.transport.requests
from google.oauth2 import id_token
from pydantic import BaseModel
import os
from datetime import timedelta

import crud, models, schemas
from auth_deps import get_current_active_user, get_password_hash, verify_password, create_access_token, get_current_user
from database import engine, get_db

app = FastAPI(title="Auth Microservice")

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")

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

@app.post("/auth/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = get_password_hash(user.password) if user.password else None
    return crud.create_user(db=db, user=user, hashed_password=hashed_password)

@app.post("/auth/token", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, email=form_data.username)
    if not user or not user.hashed_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    
    access_token_expires = timedelta(minutes=60*24)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/auth/google")
def google_auth(request: GoogleAuthRequest, db: Session = Depends(get_db)):
    try:
        idinfo = id_token.verify_oauth2_token(request.token, google.auth.transport.requests.Request(), GOOGLE_CLIENT_ID)
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

@app.get("/users/me", response_model=schemas.UserResponse)
def read_users_me(current_user: models.User = Depends(get_current_active_user)):
    return current_user

# Admin specific endpoint
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
