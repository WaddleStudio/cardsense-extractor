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


class SubcategoryEnum(str, Enum):
    GENERAL = "GENERAL"
    # ENTERTAINMENT
    MOVIE = "MOVIE"
    THEME_PARK = "THEME_PARK"
    VENUE = "VENUE"
    STREAMING = "STREAMING"
    # DINING
    DELIVERY = "DELIVERY"
    RESTAURANT = "RESTAURANT"
    CAFE = "CAFE"
    HOTEL_DINING = "HOTEL_DINING"
    # SHOPPING
    DEPARTMENT = "DEPARTMENT"
    WAREHOUSE = "WAREHOUSE"
    ELECTRONICS = "ELECTRONICS"
    DRUGSTORE = "DRUGSTORE"
    # ONLINE
    ECOMMERCE = "ECOMMERCE"
    SUBSCRIPTION = "SUBSCRIPTION"
    INTERNATIONAL_ECOMMERCE = "INTERNATIONAL_ECOMMERCE"
    AI_TOOL = "AI_TOOL"
    # TRAVEL / TRANSPORT
    RIDESHARE = "RIDESHARE"
    AIRLINE = "AIRLINE"
    HOTEL = "HOTEL"
    TRAVEL_PLATFORM = "TRAVEL_PLATFORM"
    TRAVEL_AGENCY = "TRAVEL_AGENCY"
    OVERSEAS_IN_STORE = "OVERSEAS_IN_STORE"
    # LIFESTYLE / ESSENTIALS
    EV_CHARGING = "EV_CHARGING"
    PARKING = "PARKING"
    SUPERMARKET = "SUPERMARKET"
    CONVENIENCE_STORE = "CONVENIENCE_STORE"
    HOME_LIVING = "HOME_LIVING"
    GAS_STATION = "GAS_STATION"


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


class RecommendationScopeEnum(str, Enum):
    RECOMMENDABLE = "RECOMMENDABLE"
    CATALOG_ONLY = "CATALOG_ONLY"
    FUTURE_SCOPE = "FUTURE_SCOPE"


class EligibilityTypeEnum(str, Enum):
    GENERAL = "GENERAL"
    PROFESSION_SPECIFIC = "PROFESSION_SPECIFIC"
    BUSINESS = "BUSINESS"


class PromotionCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., min_length=3)
    value: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1, max_length=120)


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
    subcategory: SubcategoryEnum = Field(default=SubcategoryEnum.GENERAL)
    channel: Optional[str] = Field(default=None)
    cashbackType: CashbackTypeEnum
    cashbackValue: Decimal = Field(..., ge=Decimal("0.00"), decimal_places=2, max_digits=10)
    minAmount: int = Field(default=0, ge=0)
    maxCashback: Optional[int] = Field(default=None, ge=0)
    frequencyLimit: FrequencyLimitEnum = Field(default=FrequencyLimitEnum.NONE)
    requiresRegistration: bool = Field(default=False)
    recommendationScope: RecommendationScopeEnum = Field(default=RecommendationScopeEnum.RECOMMENDABLE)
    eligibilityType: EligibilityTypeEnum = Field(default=EligibilityTypeEnum.GENERAL)
    validFrom: date
    validUntil: date
    conditions: List[PromotionCondition] = Field(default_factory=list)
    excludedConditions: List[PromotionCondition] = Field(default_factory=list)
    sourceUrl: HttpUrl
    rawTextHash: str = Field(..., min_length=32)
    summary: str = Field(..., min_length=3, max_length=300)
    extractorVersion: str = Field(..., min_length=3)
    extractedAt: datetime
    confidence: float = Field(..., ge=0.0, le=1.0)
    status: str = Field(default="ACTIVE")
    planId: Optional[str] = Field(default=None, min_length=3)

    @field_validator("bankCode", "cardCode", "bankName", "cardName", "title", "summary", "status", "cardStatus")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        return value.strip()

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
