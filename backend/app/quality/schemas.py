from typing import Literal

from pydantic import BaseModel, Field, field_validator


class YesNoDecision(BaseModel):
    decision: Literal["YES", "NO"]
    reason: str = ""

    @field_validator("decision", mode="before")
    @classmethod
    def normalize_decision(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip().upper()
        return value

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()


class QualityEvaluation(BaseModel):
    relevant: YesNoDecision
    complete: YesNoDecision
    escalate: YesNoDecision


class QualityResult(BaseModel):
    relevant: YesNoDecision
    complete: YesNoDecision
    escalate: YesNoDecision
    output_valid: bool = True
    provider: str = "ollama"
    quality_score: float = Field(ge=0, le=1)
    quality_reason: str

    @property
    def escalation_required(self) -> bool:
        return self.output_valid and self.escalate.decision == "YES"
