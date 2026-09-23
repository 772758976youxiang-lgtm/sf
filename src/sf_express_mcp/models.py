"""Validated input contracts exposed by the MCP tools."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Contact(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    mobile: str = Field(pattern=r"^\+?[0-9][0-9 -]{5,19}$")
    province: str = Field(min_length=1, max_length=30)
    city: str = Field(min_length=1, max_length=100)
    county: str | None = Field(default=None, max_length=30)
    address: str = Field(min_length=1, max_length=200)

    @field_validator("name", "province", "city", "county", "address")
    @classmethod
    def trim_nonempty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class Cargo(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    count: int = Field(default=1, ge=1)
    weight_kg: float | None = Field(default=None, gt=0)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class CreateOrderInput(BaseModel):
    order_id: str = Field(min_length=1, max_length=64)
    sender: Contact
    recipient: Contact
    cargo: list[Cargo] = Field(min_length=1)
    parcel_qty: int = Field(default=1, ge=1, le=999)
    total_weight_kg: float | None = Field(default=None, gt=0)
    pay_method: Literal[1, 2, 3] = 1
    express_type_id: int | None = Field(default=None, gt=0)
    monthly_card: str | None = Field(default=None, max_length=20)
    pickup_time: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
    request_pickup: bool = False
    remark: str | None = Field(default=None, max_length=100)

    @field_validator("order_id")
    @classmethod
    def trim_order_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class TrackInput(BaseModel):
    tracking_type: Literal["waybill", "order"]
    tracking_number: str = Field(min_length=1, max_length=64)

    @field_validator("tracking_number")
    @classmethod
    def trim_tracking_number(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value
