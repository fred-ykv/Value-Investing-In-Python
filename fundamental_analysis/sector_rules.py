"""Sector classification and model selection rules."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from .config import COMPANY_PROFILE, CompanyType

FINANCIAL_KEYWORDS = ("financial", "bank", "banks", "capital markets", "asset management", "insurance", "mortgage", "credit")
GROWTH_TECH_KEYWORDS = ("technology", "software", "semiconductor", "internet", "cloud", "ai", "data", "electric vehicle", "ev")
TRADITIONAL_BUSINESS_MODELS = ("traditional_auto", "legacy_auto", "industrial", "consumer_staples")
GROWTH_BUSINESS_MODELS = ("ev_pure_play", "saas", "cloud", "ai_platform", "fabless_semiconductor")


@dataclass(frozen=True)
class CompanyClassification:
    company_type: CompanyType
    business_model: str
    rule_code: str
    rationale: str


def classify_company(info: Mapping[str, object], has_negative_fcf: bool = False) -> CompanyType:
    return classify_company_profile(info, has_negative_fcf).company_type


def classify_company_profile(
    info: Mapping[str, object],
    has_negative_fcf: bool = False,
) -> CompanyClassification:
    sector = str(info.get("sector", "") or "").lower()
    industry = str(info.get("industry", "") or "").lower()
    ticker = str(info.get("ticker", info.get("symbol", "")) or "").upper().strip()
    explicit_business_model = str(info.get("business_model", "") or "").lower().strip()
    text = " ".join(
        str(info.get(name, "") or "").lower()
        for name in (
            "sector",
            "industry",
            "longBusinessSummary",
            "shortName",
            "longName",
        )
    )
    if any(_matches_keyword(text, key) for key in FINANCIAL_KEYWORDS):
        return CompanyClassification(
            CompanyType.FINANCIAL,
            explicit_business_model or "financial_institution",
            "financial_sector",
            "Setor ou industria financeira exige modelos proprios de capital e patrimonio.",
        )
    if explicit_business_model in TRADITIONAL_BUSINESS_MODELS:
        return CompanyClassification(
            CompanyType.TRADITIONAL,
            explicit_business_model,
            "explicit_traditional_business_model",
            "Modelo de negocio tradicional informado explicitamente.",
        )
    if explicit_business_model in GROWTH_BUSINESS_MODELS:
        return CompanyClassification(
            CompanyType.GROWTH_TECH,
            explicit_business_model,
            "explicit_growth_business_model",
            "Modelo de negocio growth/tech informado explicitamente.",
        )

    override = dict(COMPANY_PROFILE.business_model_by_ticker).get(ticker)
    if override in GROWTH_BUSINESS_MODELS:
        return CompanyClassification(
            CompanyType.GROWTH_TECH,
            override,
            "audited_ticker_override",
            "Ticker consta na taxonomia auditavel de modelos de negocio growth/tech.",
        )

    if any(keyword in text for keyword in COMPANY_PROFILE.ev_pure_play_keywords):
        return CompanyClassification(
            CompanyType.GROWTH_TECH,
            "ev_pure_play",
            "ev_pure_play_description",
            "Descricao operacional identifica fabricante pure-play de veiculos eletricos.",
        )
    if any(_matches_keyword(f"{sector} {industry}", key) for key in GROWTH_TECH_KEYWORDS):
        return CompanyClassification(
            CompanyType.GROWTH_TECH,
            "growth_tech",
            "growth_sector_or_industry",
            "Setor ou industria corresponde a taxonomia growth/tech.",
        )
    return CompanyClassification(
        CompanyType.TRADITIONAL,
        explicit_business_model or "traditional",
        "traditional_default",
        (
            "Sem evidencia suficiente para aplicar modelos growth/tech; "
            "classificacao conservadora como empresa tradicional."
            if has_negative_fcf
            else "Setor e modelo de negocio tratados como empresa tradicional."
        ),
    )


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
