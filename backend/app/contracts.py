from decimal import Decimal
import re
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Invoice(StrictModel):
    invoice_id: str = Field(min_length=1, max_length=100)
    po_number: str = Field(pattern=r'^PO-\d+$', max_length=50)
    vendor_name: str = Field(min_length=1, max_length=200)
    billed_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Literal['USD']
    description: str | None = None
    invoice_date: str | None = None
    issues: list[str] = Field(default_factory=list)

    @field_validator('billed_amount', mode='before')
    @classmethod
    def money(cls, value):
        if isinstance(value, str):
            if not re.fullmatch(r'\$?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?', value):
                raise ValueError('Malformed monetary amount')
            return value.replace('$', '').replace(',', '')
        if isinstance(value, (float, bool)):
            raise ValueError('Amounts must be decimal strings')
        return value

    @field_validator('vendor_name')
    @classmethod
    def one_line(cls, value):
        if '\n' in value or not value.strip():
            raise ValueError('Vendor must be one nonempty line')
        return value.strip()

class Citation(StrictModel):
    policy_id: str
    version: str

class Explanation(StrictModel):
    summary: str = Field(min_length=1, max_length=2000)
    citations: list[Citation]
    evidence_status: Literal['sufficient', 'missing', 'irrelevant', 'conflicting', 'insufficient']

class ToolResult(StrictModel):
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

