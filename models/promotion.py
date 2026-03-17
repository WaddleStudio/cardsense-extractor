from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl, condecimal, constr, conint
from datetime import date, datetime

class CategoryEnum(str, Enum):
    dining = "dining"
    travel = "travel"
    online_shopping = "online_shopping"
    groceries = "groceries"
    fuel = "fuel"
    entertainment = "entertainment"
    other = "other"

class ChannelEnum(str, Enum):
    online = "online"
    offline = "offline"
    all = "all"

class RewardTypeEnum(str, Enum):
    cashback = "cashback"
    points = "points"
    miles = "miles"

class FrequencyLimitEnum(str, Enum):
    monthly = "monthly"
    quarterly = "quarterly"
    yearly = "yearly"
    once = "once"

class PromotionNormalized(BaseModel):
    """
    Pydantic model for Normalized Promotion, aligned with cardsense-contracts.
    """
    promo_id: str = Field(..., description="Stable logical ID for the promotion")
    promo_version_id: str = Field(..., description="Immutable version ID")
    card_id: str = Field(..., description="ID of the credit card")
    bank: str = Field(..., description="Name of the issuing bank")
    
    categories: List[CategoryEnum] = Field(..., description="List of categories", min_items=0)
    channel: ChannelEnum = Field(..., description="Channel where the promotion is applicable")
    
    start_date: Optional[date] = Field(None, description="Start date (YYYY-MM-DD)")
    end_date: Optional[date] = Field(None, description="End date (YYYY-MM-DD)")
    
    min_amount: Optional[int] = Field(None, ge=0, description="Minimum spend in smallest currency unit")
    
    reward_type: Optional[RewardTypeEnum] = Field(None, description="Type of reward")
    reward_rate: Optional[float] = Field(None, ge=0.0, le=1.0, description="Reward rate as decimal")
    reward_cap: Optional[int] = Field(None, ge=0, description="Max reward amount")
    
    frequency_limit: Optional[FrequencyLimitEnum] = Field(None, description="Frequency limit")
    requires_registration: bool = Field(False, description="Whether registration is required")
    
    excluded_conditions: List[str] = Field(default_factory=list, description="Excluded conditions")
    
    source_url: Optional[HttpUrl] = Field(None, description="URL of origin")
    summary: Optional[str] = Field(None, max_length=300, description="Human-readable summary")
    
    raw_text_hash: str = Field(..., description="Hash of raw text")
    extractor_version: str = Field(..., description="Extractor version")
    extracted_at: datetime = Field(..., description="Extraction timestamp")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")

    class Config:
        use_enum_values = True
        extra = "forbid" # Strict schema enforcement
