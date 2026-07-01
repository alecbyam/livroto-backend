from fastapi import APIRouter, Depends, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.modules.auth.schemas import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    OTPRequest,
    OTPVerifyRequest,
    ChangePasswordRequest,
)
from app.modules.auth import service
from app.core.security import generate_otp, verify_password, hash_password
from app.core.exceptions import AuthError

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user = await service.register_user(
        db=db,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        tenant_slug=body.tenant_slug,
        phone=body.phone,
    )
    return await service.login_user(db, body.email, body.password)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await service.login_user(db, body.email, body.password)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await service.refresh_access_token(db, body.refresh_token)


@router.post("/logout")
async def logout(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    await service.logout_user(db, body.refresh_token)
    return {"message": "Déconnexion réussie"}


@router.post("/otp/send")
async def send_otp(
    body: OTPRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    otp = generate_otp()
    # Stocke l'OTP dans Redis avec expiration 10 min
    from app.tasks.celery_app import redis_client
    await redis_client.setex(f"otp:{body.phone}", 600, otp)

    # Envoi SMS (Twilio) avec fallback WhatsApp
    from app.modules.notifications.twilio import twilio_client
    background_tasks.add_task(twilio_client.send_otp, body.phone, otp)

    return {"message": "Code OTP envoyé", "phone": body.phone}


@router.post("/otp/verify")
async def verify_otp(body: OTPVerifyRequest):
    from app.tasks.celery_app import redis_client
    stored = await redis_client.get(f"otp:{body.phone}")

    if not stored or stored.decode() != body.code:
        raise AuthError("Code OTP invalide ou expiré")

    await redis_client.delete(f"otp:{body.phone}")
    return {"message": "Téléphone vérifié", "verified": True}


@router.get("/me")
async def me(current_user=Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "phone": current_user.phone,
        "role": current_user.role,
        "is_verified": current_user.is_verified,
        "tenant_id": str(current_user.tenant_id),
    }


@router.put("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise AuthError("Mot de passe actuel incorrect")

    current_user.hashed_password = hash_password(body.new_password)
    return {"message": "Mot de passe modifié avec succès"}
