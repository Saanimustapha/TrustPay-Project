# app/api/v1/endpoints/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import DBSession
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserRead
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, db: DBSession):
    auth = AuthService(db)
    try:
        user = await auth.create_user(user_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return user


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: DBSession = None,  # type: ignore
):
    """
    OAuth2 compatible token login.
    Use form fields: username (=email) + password.
    """
    auth = AuthService(db)
    user = await auth.authenticate(form_data.username, form_data.password)
    if not user:
        # Generic message – never reveal whether email exists
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    tokens = auth.create_tokens(user.id)
    return Token(**tokens)