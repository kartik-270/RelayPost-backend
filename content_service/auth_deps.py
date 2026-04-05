import os
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

SECRET_KEY = os.environ.get("SECRET_KEY", "your-super-secret-production-key")
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class TokenData(BaseModel):
    user_id: str
    email: str
    role: str

def verify_token(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("email")
        role: str = payload.get("role")
        user_id: str = payload.get("sub")
        if email is None or role is None or user_id is None:
            raise credentials_exception
        token_data = TokenData(user_id=user_id, email=email, role=role)
        return token_data
    except jwt.PyJWTError:
        raise credentials_exception

def get_current_publisher(token_data: TokenData = Depends(verify_token)):
    if token_data.role not in ["publisher", "admin"]:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return token_data

def get_current_admin(token_data: TokenData = Depends(verify_token)):
    if token_data.role != "admin":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return token_data
