from datetime import time

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


class WorkingHourBase(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time = Field(description="Время начала (ЧЧ:ММ)")
    end_time: time = Field(description="Время окончания (ЧЧ:ММ)")

    @model_validator(mode="after")
    def check_end_after_start(self) -> "WorkingHourBase":
        if self.end_time <= self.start_time:
            raise ValueError("end_time должно быть позже start_time")
        return self


class WorkingHourCreate(WorkingHourBase):
    pass  # ← теперь нет сериализатора, model_dump() вернёт time


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

    @field_serializer("start_time", "end_time")  # ← сериализатор только здесь
    def serialize_time(self, value: time) -> str:
        return value.strftime("%H:%M")
