from typing import Literal

from pydantic import BaseModel, ConfigDict

Role = Literal["admin", "teacher", "student"]
Language = Literal["es", "en"]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
