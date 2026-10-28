from pydantic import BaseModel, EmailStr
from typing import Optional


class User(BaseModel):
    id: str
    username: str
    email: EmailStr
    role: str = "analyst"
    is_active: bool = True
