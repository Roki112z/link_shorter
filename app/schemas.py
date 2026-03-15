from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator, model_validator


class UserRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LinkCreateRequest(BaseModel):
    original_url: HttpUrl
    custom_alias: str | None = Field(default=None, min_length=4, max_length=50)
    expires_at: datetime | None = None

    @field_validator("custom_alias")
    @classmethod
    def validate_custom_alias(cls, value: str | None) -> str | None:
        if value is None:
            return None

        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
        if not all(char in allowed for char in value):
            raise ValueError("custom_alias может содержать только буквы, цифры, '_' и '-'")
        return value

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        if value.second != 0 or value.microsecond != 0:
            raise ValueError("expires_at должен быть с точностью до минуты (без секунд)")
        if value <= datetime.now(timezone.utc):
            raise ValueError("expires_at должен быть в будущем")
        return value


class LinkUpdateRequest(BaseModel):
    original_url: HttpUrl | None = None
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        if value.second != 0 or value.microsecond != 0:
            raise ValueError("expires_at должен быть с точностью до минуты (без секунд)")
        if value <= datetime.now(timezone.utc):
            raise ValueError("expires_at должен быть в будущем")
        return value

    @model_validator(mode="after")
    def validate_payload(self) -> "LinkUpdateRequest":
        if self.original_url is None and self.expires_at is None:
            raise ValueError("Нужно передать хотя бы одно поле: original_url или expires_at")
        return self


class LinkInfoResponse(BaseModel):
    short_code: str
    short_url: str
    original_url: str
    created_at: datetime
    expires_at: datetime | None = None


class LinkStatsResponse(BaseModel):
    short_code: str
    original_url: str
    created_at: datetime
    expires_at: datetime | None = None
    visits: int
    last_used_at: datetime | None = None


class SearchResponse(BaseModel):
    items: list[LinkInfoResponse]


class MessageResponse(BaseModel):
    message: str
