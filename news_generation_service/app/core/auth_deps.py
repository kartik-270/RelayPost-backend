"""
Auth dependencies for news_service — mirrors content_service auth_deps
but kept minimal since news_service is lighter.
"""
import os
import jwt
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional

SECRET_KEY = os.environ.get("SECRET_KEY", "your-super-secret-production-key")
ALGORITHM = "HS256"

AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://auth_service:8000")
TRACKING_SERVICE_URL = os.environ.get("TRACKING_SERVICE_URL", "http://tracking_service:8003")

TIER_HIERARCHY = {"free": 0, "plus": 1, "pro": 2}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


class TokenData(BaseModel):
    user_id: str
    email: str
    role: str
    tier: str = "free"


def verify_token(token: str = Depends(oauth2_scheme)) -> TokenData:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("email")
        role = payload.get("role")
        user_id = payload.get("sub")
        if not all([email, role, user_id]):
            raise credentials_exception
        tier = payload.get("tier", "free")
        return TokenData(user_id=user_id, email=email, role=role, tier=tier)
    except jwt.PyJWTError:
        raise credentials_exception


def verify_token_optional(token: Optional[str] = Depends(oauth2_scheme_optional)) -> Optional[TokenData]:
    if not token:
        return None
    try:
        return verify_token(token)
    except HTTPException:
        return None


def _get_verified_tier(user_id: str) -> str:
    try:
        resp = httpx.get(f"{AUTH_SERVICE_URL}/internal/tier/{user_id}", timeout=3.0)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("is_active", False):
                return data.get("tier", "free")
    except Exception as e:
        print(f"WARNING: tier check failed for {user_id}: {e}")
    return "free"


def require_tier(min_tier: str):
    def _check(token_data: TokenData = Depends(verify_token)) -> TokenData:
        verified_tier = _get_verified_tier(token_data.user_id)
        token_data.tier = verified_tier
        if TIER_HIERARCHY.get(verified_tier, 0) < TIER_HIERARCHY.get(min_tier, 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "tier_required",
                    "required_tier": min_tier,
                    "current_tier": verified_tier,
                    "message": f"This feature requires a {min_tier.title()} or higher plan.",
                    "upgrade_url": "/pricing",
                }
            )
        return token_data
    return _check


def check_and_track_usage(feature: str):
    def _check(token_data: TokenData = Depends(verify_token)) -> TokenData:
        verified_tier = _get_verified_tier(token_data.user_id)
        token_data.tier = verified_tier
        try:
            resp = httpx.post(
                f"{TRACKING_SERVICE_URL}/usage/check",
                json={"user_id": token_data.user_id, "feature": feature, "tier": verified_tier},
                timeout=3.0,
            )
            if resp.status_code == 200:
                result = resp.json()
                if not result.get("allowed", False):
                    reason = result.get("reason", "limit_exceeded")
                    if reason == "tier_blocked":
                        raise HTTPException(
                            status_code=403,
                            detail={
                                "error": "tier_required",
                                "feature": feature,
                                "current_tier": verified_tier,
                                "message": f"This feature is not available on the {verified_tier.title()} plan.",
                                "upgrade_url": "/pricing",
                            }
                        )
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "error": "usage_limit_exceeded",
                            "feature": feature,
                            "tier": verified_tier,
                            "remaining": 0,
                            "limit": result.get("limit"),
                            "reset_at": result.get("reset_at"),
                            "message": f"You've reached your {feature.replace('_', ' ')} limit for this period.",
                            "upgrade_url": "/pricing",
                        }
                    )
        except HTTPException:
            raise
        except Exception as e:
            print(f"WARNING: usage check failed: {e}")
        return token_data
    return _check


def track_usage(user_id: str, feature: str, tier: str, count: int = 1):
    try:
        httpx.post(
            f"{TRACKING_SERVICE_URL}/usage/track",
            json={"user_id": user_id, "feature": feature, "tier": tier, "count": count},
            timeout=2.0,
        )
    except Exception as e:
        print(f"WARNING: tracking failed: {e}")
