from datetime import datetime

from pydantic import BaseModel

from app.core.types import SolutionPolicy, Tone, TutorLevel


class StudentTutorSettings(BaseModel):
    level: TutorLevel
    tone: Tone
    solution_policy: SolutionPolicy


class TutorSettingsUpdate(StudentTutorSettings):
    pass


class TutorSettings(StudentTutorSettings):
    updated_at: datetime
