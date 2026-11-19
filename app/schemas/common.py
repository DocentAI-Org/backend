from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict


def _strip_nul(value: object) -> object:
    # Postgres text cannot store NUL; it is never meaningful in user input.
    return value.replace("\x00", "") if isinstance(value, str) else value


CleanText = Annotated[str, BeforeValidator(_strip_nul)]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
