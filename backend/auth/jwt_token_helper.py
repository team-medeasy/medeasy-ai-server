from fastapi import FastAPI, HTTPException, status
from fastapi.security import HTTPBearer
from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel
import os
from dotenv import load_dotenv
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

app = FastAPI()
security = HTTPBearer()
load_dotenv()

# Configuration - these should match your Spring application settings
TOKEN_SECRET_KEY = os.getenv("TOKEN_SECRET_KEY")  # 이것은 Spring의 token.secret.key와 동일해야 합니다
ALGORITHM = "HS256"  # Spring에서 사용하는 알고리즘과 동일 (SignatureAlgorithm.HS256)


class TokenPayload(BaseModel):
    user_id: Optional[str] = None
    exp: Optional[datetime] = None


def decode_token(token: str) -> Dict[str, Any]:
    """
    Spring에서 발급된 JWT 토큰을 파싱하고 검증합니다.
    """
    try:
        # JWT 토큰을 디코딩합니다.
        payload = jwt.decode(
            token,
            TOKEN_SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        # 토큰이 만료된 경우
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        # 토큰이 유효하지 않은 경우 (서명 검증 실패 등)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_user_id_from_token(token: str) -> str:
    """
    JWT 토큰에서 user_id만 추출하는 함수
    """
    try:
        payload = jwt.decode(token, TOKEN_SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("userId")
        if not user_id:
            raise ValueError("토큰에 userId가 없습니다")
        return user_id
    except jwt.ExpiredSignatureError:
        raise ValueError("만료된 토큰입니다")
    except jwt.InvalidTokenError:
        raise ValueError("유효하지 않은 토큰입니다")