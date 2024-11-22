from datetime import timedelta

from fastapi import Depends, APIRouter
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from db.database import get_session
from error_code import raise_exception, ErrorCode
from .auth import verify_password, ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token, get_current_user
from .model import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(),
                                 db: Session = Depends(get_session)):
    # 从数据库中查找用户
    user = db.exec(select(User).where(User.name == form_data.username)).first()

    # 用户不存在或密码不正确时返回错误
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise_exception(ErrorCode.LOGIN_FAILED, "账号或者密码错误")

    # 生成 JWT 令牌
    access_token = create_access_token(
        data={"sub": user.name}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post('/refresh_token')
def refresh_token(user: User = Depends(get_current_user)):
    access_token = create_access_token(
        data={"sub": user.name}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}
