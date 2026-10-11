from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    expires_in: int


class ConversationCreate(BaseModel):
    title: str = Field(default='New conversation', min_length=1, max_length=120)

    @field_validator('title')
    @classmethod
    def trim_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('Title cannot be blank')
        return value


class ConversationPatch(BaseModel):
    title: str = Field(min_length=1, max_length=120)

    @field_validator('title')
    @classmethod
    def trim_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('Title cannot be blank')
        return value


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    request_id: UUID = Field(default_factory=uuid4)

    @field_validator('content')
    @classmethod
    def trim_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('Message cannot be blank')
        return value


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    role: str
    content: str
    created_at: datetime


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationRead):
    messages: list[MessageRead]


class ChatResponse(BaseModel):
    conversation_id: str
    user_message: MessageRead
    assistant_message: MessageRead
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class UsageSummary(BaseModel):
    requests: int
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float | None = None
    note: str = 'Cost is not estimated because provider price metadata is not configured.'
