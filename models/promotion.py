from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class CategoryEnum(str, Enum):
    DINING = "DINING"
    TRANSPORT = "TRANSPORT"
    ONLINE = "ONLINE"
    OVERSEAS = "OVERSEAS"
    SHOPPING = "SHOPPING"
    GROCERY = "GROCERY"
    ENTERTAINMENT = "ENTERTAINMENT"
    OTHER = "OTHER"


class CashbackTypeEnum(str, Enum):
    PERCENT = "PERCENT"
    FIXED = "FIXED"
    POINTS = "POINTS"


class FrequencyLimitEnum(str, Enum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"
    ONCE = "ONCE"
    NONE = "NONE"


class PromotionNormalized(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    promoId: str = Field(..., min_length=8)
    promoVersionId: str = Field(..., min_length=16)
    title: str = Field(..., min_length=3, max_length=200)
    cardCode: str = Field(..., min_length=3)
    cardName: str = Field(..., min_length=3, max_length=100)
    cardStatus: str = Field(default="ACTIVE")
    annualFee: int = Field(default=0, ge=0)
    applyUrl: Optional[HttpUrl] = None
    bankCode: str = Field(..., min_length=2, max_length=20)
    bankName: str = Field(..., min_length=2, max_length=100)
    category: CategoryEnum
    channel: Optional[str] = Field(default=None)
    cashbackType: CashbackTypeEnum
    cashbackValue: Decimal = Field(..., ge=Decimal("0.00"), decimal_places=2, max_digits=5)
    minAmount: int = Field(default=0, ge=0)
    maxCashback: Optional[int] = Field(default=None, ge=0)
    frequencyLimit: FrequencyLimitEnum = Field(default=FrequencyLimitEnum.NONE)
    requiresRegistration: bool = Field(default=False)
    validFrom: date
    validUntil: date
    conditions: List[str] = Field(default_factory=list)
    excludedConditions: List[str] = Field(default_factory=list)
    sourceUrl: HttpUrl
    rawTextHash: str = Field(..., min_length=32)
    summary: str = Field(..., min_length=3, max_length=300)
    extractorVersion: str = Field(..., min_length=3)
    extractedAt: datetime
    confidence: float = Field(..., ge=0.0, le=1.0)
    status: str = Field(default="ACTIVE")

    @field_validator("bankCode", "cardCode", "bankName", "cardName", "title", "summary", "status", "cardStatus")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        return value.strip()

    @field_validator("conditions", "excludedConditions")
    @classmethod
    def normalize_string_lists(cls, value: List[str]) -> List[str]:
        return [item.strip() for item in value if item and item.strip()]

    @field_validator("cashbackValue", mode="before")
    @classmethod
    def normalize_cashback_value(cls, value: object) -> Decimal:
        if value is None or value == "":
            return value
        return Decimal(str(value)).quantize(Decimal("0.01"))

    @model_validator(mode="after")
    def validate_business_rules(self) -> "PromotionNormalized":
        if self.validFrom > self.validUntil:
            raise ValueError("validFrom must be on or before validUntil")
        if self.cashbackValue <= 0:
            raise ValueError("cashbackValue must be greater than zero")
        return self
