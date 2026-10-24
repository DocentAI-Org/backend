from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict


def _strip_nul(value: object) -> object:
    # Postgres text cannot store NUL; it is never meaningful in user input.
    return value.replace("\x00", "") if isinstance(value, str) else value


CleanText = Annotated[str, BeforeValidator(_strip_nul)]

Role = Literal["admin", "teacher", "student"]
Language = Literal["es", "en"]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
