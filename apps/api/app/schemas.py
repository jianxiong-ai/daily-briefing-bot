from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ReportField(BaseModel):
    key: str
    label: str
    type: str
    placeholder: str = ""
    help: str = ""
    required: bool = False
    recommended: bool = False
    group: str = ""


class ReportOption(BaseModel):
    name: str
    title: str
    default_env: str
    fields: List[ReportField]
    window: Dict = Field(default_factory=dict)


class ValidationIssue(BaseModel):
    level: str
    key: str
    message: str


class ValidationResult(BaseModel):
    issues: List[ValidationIssue]


class SubscriptionBase(BaseModel):
    report_type: str
    name: str = ""
    is_active: bool = True
    push_time: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    feishu_webhook: str = ""
    config: Dict[str, str] = Field(default_factory=dict)

    @field_validator("push_time")
    @classmethod
    def validate_push_time(cls, value: str) -> str:
        hour, minute = [int(part) for part in value.split(":")]
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("push_time must be a valid HH:MM time")
        return value


class SubscriptionCreate(SubscriptionBase):
    pass


class SubscriptionUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    push_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    feishu_webhook: Optional[str] = None
    config: Optional[Dict[str, str]] = None


class SubscriptionOut(SubscriptionBase):
    id: int
    created_at: datetime
    updated_at: datetime
    last_run_at: Optional[datetime] = None
    last_status: str = ""
    last_message: str = ""
    warnings: List[str] = Field(default_factory=list)


class RunRequest(BaseModel):
    render_only: bool = True
    send: bool = False
    digest_date: str = ""


class RunOut(BaseModel):
    id: int
    subscription_id: int
    report_type: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    output_path: str = ""
    message: str = ""


class SchedulerStatus(BaseModel):
    enabled: bool
    timezone: str
    jobs: List[dict]
