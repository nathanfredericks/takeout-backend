from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    authenticate_user,
    create_access_token,
    get_password_hash,
)
from db import SessionDep
from models import LoginSchema, Token, User, UserCreateSchema, UserReadSchema
from routers.dependencies import AnyUser

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/register", response_model=UserReadSchema)
async def register(user: UserCreateSchema, session: SessionDep):
    existing_user = session.execute(
        select(User).where(User.email == user.email)
    ).scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    db_user = User(
        name=user.name,
        email=user.email,
        phone_number=user.phone_number,
        role=user.role,
        password=get_password_hash(user.password),
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


@router.post("/login", response_model=Token)
async def login(login_data: LoginSchema, session: SessionDep):
    user = authenticate_user(session, login_data.email, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserReadSchema)
async def get_current_user_profile(current_user: AnyUser):
    return current_user
