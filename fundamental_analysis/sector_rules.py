"""Sector classification and model selection rules."""
from __future__ import annotations

import re
from typing import Mapping

from .config import CompanyType

FINANCIAL_KEYWORDS = ("financial", "bank", "banks", "capital markets", "asset management", "insurance", "mortgage", "credit")
GROWTH_TECH_KEYWORDS = ("technology", "software", "semiconductor", "internet", "cloud", "ai", "data", "electric vehicle", "ev")
TRADITIONAL_BUSINESS_MODELS = ("traditional_auto", "legacy_auto", "industrial", "consumer_staples")
GROWTH_BUSINESS_MODELS = ("ev_pure_play", "saas", "cloud", "ai_platform", "fabless_semiconductor")


def classify_company(info: Mapping[str, object], has_negative_fcf: bool = False) -> CompanyType:
    sector = str(info.get("sector", "") or "").lower()
    industry = str(info.get("industry", "") or "").lower()
    business_model = str(info.get("business_model", "") or "").lower()
    text = f"{sector} {industry}"
    if any(_matches_keyword(text, key) for key in FINANCIAL_KEYWORDS):
        return CompanyType.FINANCIAL
    if business_model in TRADITIONAL_BUSINESS_MODELS:
        return CompanyType.TRADITIONAL
    if business_model in GROWTH_BUSINESS_MODELS:
        return CompanyType.GROWTH_TECH
    if any(_matches_keyword(text, key) for key in GROWTH_TECH_KEYWORDS):
        return CompanyType.GROWTH_TECH
    if has_negative_fcf and any(_matches_keyword(text, key) for key in GROWTH_TECH_KEYWORDS):
        return CompanyType.GROWTH_TECH
    return CompanyType.TRADITIONAL


def preferred_models(company_type: CompanyType) -> tuple[str, ...]:
    if company_type == CompanyType.FINANCIAL:
        return ("residual_income", "ddm", "pb_roe_ke")
    if company_type == CompanyType.GROWTH_TECH:
        return ("growth_tech", "reverse_dcf", "ev_sales")
    return ("dcf_fcff", "eva", "graham")


def _matches_keyword(text: str, keyword: str) -> bool:
    if len(keyword) <= 2:
        return re.search(rf"(^|[^a-z0-9]){re.escape(keyword)}([^a-z0-9]|$)", text) is not None
    return keyword in text
