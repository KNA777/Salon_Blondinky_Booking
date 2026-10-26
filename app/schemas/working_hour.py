from datetime import time

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkingHourBase(BaseModel):
    """Рабочий интервал: день недели и «настенное» время салона (Time без часового пояса)."""

    weekday: int = Field(ge=0, le=6)  # 0 = понедельник, 6 = воскресенье
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def check_end_after_start(self) -> "WorkingHourBase":
        if self.end_time <= self.start_time:
            raise ValueError("end_time должно быть позже start_time")
        return self


class WorkingHourCreate(WorkingHourBase):
    pass


class WorkingHourUpdate(BaseModel):
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None

    @model_validator(mode="after")
    def check_end_after_start(self) -> "WorkingHourUpdate":
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("end_time должно быть позже start_time")
        return self


class WorkingHourOut(WorkingHourBase):
    id: int
    master_id: int

    model_config = ConfigDict(from_attributes=True)
