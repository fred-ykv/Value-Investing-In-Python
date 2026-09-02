"""Sector classification and model selection rules."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from .config import COMPANY_PROFILE, CompanyType

FINANCIAL_KEYWORDS = ("financial", "bank", "banks", "capital markets", "asset management", "insurance", "mortgage", "credit")
GROWTH_TECH_KEYWORDS = ("technology", "software", "semiconductor", "internet", "cloud", "ai", "data", "electric vehicle", "ev")
TRADITIONAL_BUSINESS_MODELS = (
    "traditional_auto",
    "legacy_auto",
    "industrial",
    "consumer_staples",
    "steel_producer",
    "metal_fabrication",
    "physical_retail",
    "large_pharma",
    "reit",
)
GROWTH_BUSINESS_MODELS = (
    "ev_pure_play",
    "saas",
    "software_platform",
    "cloud",
    "ai_platform",
    "semiconductor",
    "fabless_semiconductor",
    "marketplace",
)

INDUSTRY_BUSINESS_MODELS = (
    (("banks - diversified", "banks - regional", "bank"), "bank"),
    (("insurance",), "insurance"),
    (("software - infrastructure",), "software_platform"),
    (("software - application",), "saas"),
    (("semiconductor",), "semiconductor"),
    (("internet retail",), "marketplace"),
    (("auto manufacturers", "automobile manufacturers"), "traditional_auto"),
    (("steel",), "steel_producer"),
    (("metal fabrication", "aluminum"), "metal_fabrication"),
    (("discount stores", "home improvement retail"), "physical_retail"),
    (("reit",), "reit"),
    (("drug manufacturers - general",), "large_pharma"),
)


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
    inferred_business_model = infer_industry_business_model(industry)
    sector_industry_text = f"{sector} {industry}"
    descriptive_text = " ".join(
        str(info.get(name, "") or "").lower()
        for name in (
            "sector",
            "industry",
            "longBusinessSummary",
            "shortName",
            "longName",
        )
    )
    if any(_matches_keyword(sector_industry_text, key) for key in FINANCIAL_KEYWORDS):
        return CompanyClassification(
            CompanyType.FINANCIAL,
            explicit_business_model or inferred_business_model or "financial_institution",
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

    if (
        "auto" in industry
        and any(
            keyword in descriptive_text
            for keyword in COMPANY_PROFILE.ev_pure_play_keywords
        )
    ):
        return CompanyClassification(
            CompanyType.GROWTH_TECH,
            "ev_pure_play",
            "ev_pure_play_description",
            "Descricao operacional identifica fabricante pure-play de veiculos eletricos.",
        )
    if any(_matches_keyword(sector_industry_text, key) for key in GROWTH_TECH_KEYWORDS):
        return CompanyClassification(
            CompanyType.GROWTH_TECH,
            inferred_business_model or "growth_tech",
            "growth_sector_or_industry",
            "Setor ou industria corresponde a taxonomia growth/tech.",
        )
    return CompanyClassification(
        CompanyType.TRADITIONAL,
        explicit_business_model or inferred_business_model or "traditional",
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


def infer_industry_business_model(industry: str) -> str:
    normalized = industry.strip().lower()
    for keywords, business_model in INDUSTRY_BUSINESS_MODELS:
        if any(keyword in normalized for keyword in keywords):
            return business_model
    return ""
