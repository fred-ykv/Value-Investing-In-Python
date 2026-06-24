"""Sector classification and model selection rules."""
from __future__ import annotations

from typing import Mapping

from .config import CompanyType

FINANCIAL_KEYWORDS = ("financial", "bank", "banks", "capital markets", "asset management", "insurance", "mortgage", "credit")
GROWTH_TECH_KEYWORDS = ("technology", "software", "semiconductor", "internet", "cloud", "ai", "data", "electric vehicle", "auto manufacturers", "automobile", "ev")


def classify_company(info: Mapping[str, object], has_negative_fcf: bool = False) -> CompanyType:
    sector = str(info.get("sector", "") or "").lower()
    industry = str(info.get("industry", "") or "").lower()
    text = f"{sector} {industry}"
    if any(key in text for key in FINANCIAL_KEYWORDS):
        return CompanyType.FINANCIAL
    if any(key in text for key in GROWTH_TECH_KEYWORDS):
        return CompanyType.GROWTH_TECH
    if has_negative_fcf and any(key in text for key in GROWTH_TECH_KEYWORDS):
        return CompanyType.GROWTH_TECH
    return CompanyType.TRADITIONAL


def preferred_models(company_type: CompanyType) -> tuple[str, ...]:
    if company_type == CompanyType.FINANCIAL:
        return ("residual_income", "ddm", "pb_roe_ke")
    if company_type == CompanyType.GROWTH_TECH:
        return ("growth_tech", "reverse_dcf", "ev_sales")
    return ("dcf_fcff", "eva", "graham")
