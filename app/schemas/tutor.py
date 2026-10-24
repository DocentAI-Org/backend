from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Level = Literal["basic", "intermediate", "advanced"]
Tone = Literal["friendly", "neutral", "formal"]
SolutionPolicy = Literal["direct", "hints_first", "hints_only"]


class StudentTutorSettings(BaseModel):
    level: Level
    tone: Tone
    solution_policy: SolutionPolicy


class TutorSettingsUpdate(StudentTutorSettings):
    pass


class TutorSettings(StudentTutorSettings):
    updated_at: datetime
