from pydantic import BaseModel, EmailStr, field_validator
import re


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: str | None = None
    tenant_slug: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Le mot de passe doit contenir au moins 8 caractères")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Le mot de passe doit contenir au moins une majuscule")
        if not re.search(r"\d", v):
            raise ValueError("Le mot de passe doit contenir au moins un chiffre")
        return v

    @field_validator("phone")
    @classmethod
    def phone_format(cls, v: str | None) -> str | None:
        if v and not re.match(r"^\+?[0-9]{9,15}$", v):
            raise ValueError("Format de téléphone invalide (ex: +243XXXXXXXXX)")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # secondes


class RefreshRequest(BaseModel):
    refresh_token: str


class OTPRequest(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def phone_format(cls, v: str) -> str:
        if not re.match(r"^\+?[0-9]{9,15}$", v):
            raise ValueError("Format téléphone invalide")
        return v


class OTPVerifyRequest(BaseModel):
    phone: str
    code: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Minimum 8 caractères")
        return v
