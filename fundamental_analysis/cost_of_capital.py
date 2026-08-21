"""Auditable cost-of-capital calculation for valuation models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .config import CompanyType, MARKET
from .data_sources import MetricValue, clamp, confidence_for_source, metric_value, safe_float


@dataclass(frozen=True)
class CostOfCapitalResult:
    company_type: str
    method: str
    discount_rate: float
    discount_rate_label: str
    wacc: float | None
    calculated_wacc: float | None
    cost_of_equity: float
    pre_tax_cost_of_debt: float | None
    after_tax_cost_of_debt: float | None
    risk_free_rate: float
    beta: float
    equity_risk_premium: float
    tax_rate: float | None
    market_value_equity: float | None
    debt_value: float | None
    equity_weight: float | None
    debt_weight: float | None
    confidence: float
    is_fallback: bool
    sources: dict[str, str] = field(default_factory=dict)
    component_confidences: dict[str, float] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def discount_rate_metric(self) -> MetricValue:
        source = "fallback" if self.is_fallback else "derived"
        return metric_value(
            "wacc" if self.discount_rate_label == "WACC" else "ke",
            self.discount_rate,
            source,
            f"{self.discount_rate_label}: {self.method}",
            basis="fallback" if self.is_fallback else "derived",
            is_fallback=self.is_fallback,
            formula="cost_of_capital_audit",
            confidence=self.confidence,
        )


@dataclass(frozen=True)
class _Observation:
    value: float | None
    source: str
    confidence: float
    is_fallback: bool = False


def calculate_cost_of_capital(
    company_type: CompanyType,
    values: Mapping[str, MetricValue],
    market_data: Mapping[str, object],
    source: str = "manual",
) -> CostOfCapitalResult:
    notes: list[str] = []
    sources: dict[str, str] = {}
    component_confidences: dict[str, float] = {}

    risk_free = _input_observation(market_data.get("risk_free_rate"), source)
    if risk_free.value is None:
        risk_free = _Observation(MARKET.risk_free_rate, MARKET.risk_free_rate_source, confidence_for_source("fallback"), True)
    sources["risk_free_rate"] = risk_free.source
    component_confidences["risk_free_rate"] = risk_free.confidence

    equity_risk_premium = _input_observation(market_data.get("equity_risk_premium"), source)
    if equity_risk_premium.value is None:
        equity_risk_premium = _Observation(MARKET.equity_risk_premium, MARKET.equity_risk_premium_source, confidence_for_source("fallback"), True)
    sources["equity_risk_premium"] = equity_risk_premium.source
    component_confidences["equity_risk_premium"] = equity_risk_premium.confidence

    beta = _input_observation(market_data.get("beta"), source)
    if beta.value is None:
        beta = _metric_observation(values.get("beta"))
    if beta.value is None:
        beta = _Observation(MARKET.default_beta, "Beta padrao de config.py", confidence_for_source("fallback"), True)
        notes.append("Beta indisponivel; foi usado o beta padrao configurado.")
    bounded_beta = clamp(beta.value, MARKET.min_beta, MARKET.max_beta)
    if bounded_beta != beta.value:
        notes.append(f"Beta limitado de {beta.value:.2f} para {bounded_beta:.2f} pela faixa de validacao.")
        beta = _Observation(bounded_beta, beta.source, max(0.0, beta.confidence - 0.15), True)
    sources["beta"] = beta.source
    component_confidences["beta"] = beta.confidence

    explicit_ke = _input_observation(market_data.get("ke"), source)
    if explicit_ke.value is not None:
        cost_of_equity = _bounded_rate(explicit_ke.value)
        ke_confidence = explicit_ke.confidence
        ke_fallback = explicit_ke.is_fallback
        sources["cost_of_equity"] = f"{explicit_ke.source}; Ke informado"
    else:
        cost_of_equity = _bounded_rate(risk_free.value + beta.value * equity_risk_premium.value)
        ke_confidence = _average_confidence(risk_free, beta, equity_risk_premium)
        ke_fallback = risk_free.is_fallback or beta.is_fallback or equity_risk_premium.is_fallback
        sources["cost_of_equity"] = "CAPM: taxa livre de risco + beta x premio de risco"
    component_confidences["cost_of_equity"] = ke_confidence

    if company_type == CompanyType.FINANCIAL:
        notes.append("Bancos e financeiras usam custo do patrimonio (Ke); WACC nao e aplicado aos modelos de Lucro Residual e DDM.")
        component_confidences["discount_rate"] = ke_confidence
        return CostOfCapitalResult(
            company_type=company_type.value,
            method="ke_for_financial_company",
            discount_rate=cost_of_equity,
            discount_rate_label="Custo do patrimonio (Ke)",
            wacc=None,
            calculated_wacc=None,
            cost_of_equity=cost_of_equity,
            pre_tax_cost_of_debt=None,
            after_tax_cost_of_debt=None,
            risk_free_rate=risk_free.value,
            beta=beta.value,
            equity_risk_premium=equity_risk_premium.value,
            tax_rate=safe_float(values.get("tax_rate")),
            market_value_equity=None,
            debt_value=None,
            equity_weight=None,
            debt_weight=None,
            confidence=ke_confidence,
            is_fallback=ke_fallback,
            sources=sources,
            component_confidences=component_confidences,
            notes=tuple(notes),
        )

    equity = _market_equity_observation(values)
    debt = _metric_observation(values.get("total_debt"))
    tax_rate = _metric_observation(values.get("tax_rate"))
    sources["market_value_equity"] = equity.source
    sources["debt_value"] = debt.source
    sources["tax_rate"] = tax_rate.source
    component_confidences["market_value_equity"] = equity.confidence
    component_confidences["debt_value"] = debt.confidence
    component_confidences["tax_rate"] = tax_rate.confidence

    explicit_cost_of_debt = _input_observation(market_data.get("cost_of_debt"), source)
    if explicit_cost_of_debt.value is not None:
        pre_tax_cost_of_debt = _bounded_debt_rate(explicit_cost_of_debt.value)
        debt_cost_confidence = explicit_cost_of_debt.confidence
        debt_cost_fallback = explicit_cost_of_debt.is_fallback
        sources["pre_tax_cost_of_debt"] = f"{explicit_cost_of_debt.source}; custo da divida informado"
    else:
        pre_tax_cost_of_debt, debt_cost_confidence, debt_cost_fallback, debt_cost_source = _estimate_cost_of_debt(
            values,
            debt,
            risk_free,
        )
        sources["pre_tax_cost_of_debt"] = debt_cost_source
    component_confidences["pre_tax_cost_of_debt"] = debt_cost_confidence

    resolved_tax_rate = clamp(tax_rate.value if tax_rate.value is not None else 0.0, 0.0, 0.45)
    if tax_rate.value is None:
        notes.append("Aliquota de imposto indisponivel; beneficio fiscal da divida foi assumido como zero.")
    after_tax_cost_of_debt = pre_tax_cost_of_debt * (1.0 - resolved_tax_rate)
    component_confidences["after_tax_cost_of_debt"] = min(debt_cost_confidence, tax_rate.confidence) if debt.value else debt_cost_confidence

    capital_total = None
    if equity.value is not None and equity.value > 0 and debt.value is not None and debt.value >= 0:
        capital_total = equity.value + debt.value
    if capital_total and capital_total > 0:
        equity_weight = equity.value / capital_total
        debt_weight = debt.value / capital_total
        calculated_wacc = cost_of_equity * equity_weight + after_tax_cost_of_debt * debt_weight
        capital_confidence = _capital_confidence(
            equity,
            debt,
            ke_confidence,
            debt_cost_confidence,
            tax_rate.confidence,
            equity_weight,
            debt_weight,
        )
        component_confidences["capital_weights"] = (equity.confidence + debt.confidence) / 2.0
        component_confidences["calculated_wacc"] = capital_confidence
    else:
        equity_weight = None
        debt_weight = None
        calculated_wacc = None
        capital_confidence = max(0.0, ke_confidence - 0.25)
        notes.append("Estrutura de capital incompleta; WACC nao pode ser calculado com seguranca.")

    explicit_wacc = _input_observation(market_data.get("wacc"), source)
    if explicit_wacc.value is not None:
        final_rate = _bounded_rate(explicit_wacc.value)
        final_wacc = final_rate
        confidence = explicit_wacc.confidence
        is_fallback = explicit_wacc.is_fallback
        method = "explicit_wacc_override"
        sources["discount_rate"] = f"{explicit_wacc.source}; WACC informado"
        if calculated_wacc is not None:
            notes.append(f"WACC informado prevaleceu; WACC calculado para comparacao foi {calculated_wacc:.2%}.")
    elif calculated_wacc is not None:
        final_rate = calculated_wacc
        final_wacc = calculated_wacc
        confidence = capital_confidence
        debt_inputs_are_fallback = bool(debt_weight) and (debt_cost_fallback or tax_rate.is_fallback)
        is_fallback = ke_fallback or debt_inputs_are_fallback or equity.is_fallback or debt.is_fallback
        method = "market_value_wacc"
        sources["discount_rate"] = "WACC calculado pelo modelo"
    else:
        final_rate = cost_of_equity
        final_wacc = None
        confidence = capital_confidence
        is_fallback = True
        method = "ke_proxy_missing_capital_structure"
        sources["discount_rate"] = "Ke usado como proxy por falta de estrutura de capital completa"
    component_confidences["discount_rate"] = confidence

    return CostOfCapitalResult(
        company_type=company_type.value,
        method=method,
        discount_rate=final_rate,
        discount_rate_label="WACC" if final_wacc is not None else "Custo do patrimonio (proxy)",
        wacc=final_wacc,
        calculated_wacc=calculated_wacc,
        cost_of_equity=cost_of_equity,
        pre_tax_cost_of_debt=pre_tax_cost_of_debt,
        after_tax_cost_of_debt=after_tax_cost_of_debt,
        risk_free_rate=risk_free.value,
        beta=beta.value,
        equity_risk_premium=equity_risk_premium.value,
        tax_rate=resolved_tax_rate,
        market_value_equity=equity.value,
        debt_value=debt.value,
        equity_weight=equity_weight,
        debt_weight=debt_weight,
        confidence=confidence,
        is_fallback=is_fallback,
        sources=sources,
        component_confidences=component_confidences,
        notes=tuple(notes),
    )


def _input_observation(value: object, source: str) -> _Observation:
    if isinstance(value, MetricValue):
        return _metric_observation(value)
    numeric = safe_float(value)
    if numeric is None:
        return _Observation(None, "Indisponivel", 0.0)
    return _Observation(numeric, f"Entrada {source}", confidence_for_source(source), source == "fallback")


def _metric_observation(metric: MetricValue | None) -> _Observation:
    if metric is None or not metric.is_available:
        return _Observation(None, "Indisponivel", 0.0)
    detail = metric.source_document or metric.source
    return _Observation(metric.value, detail, metric.confidence, metric.is_fallback)


def _market_equity_observation(values: Mapping[str, MetricValue]) -> _Observation:
    market_cap = _metric_observation(values.get("market_cap"))
    if market_cap.value is not None and market_cap.value > 0:
        return market_cap
    price = values.get("price")
    shares = values.get("shares")
    if price and shares and price.is_available and shares.is_available and price.value > 0 and shares.value > 0:
        return _Observation(
            price.value * shares.value,
            "Preco atual x numero de acoes",
            (price.confidence + shares.confidence) / 2.0,
        )
    book_equity = _metric_observation(values.get("equity"))
    if book_equity.value is not None and book_equity.value > 0:
        return _Observation(book_equity.value, "Patrimonio contabil usado como fallback", max(0.0, book_equity.confidence - 0.25), True)
    return _Observation(None, "Valor de mercado do patrimonio indisponivel", 0.0, True)


def _estimate_cost_of_debt(
    values: Mapping[str, MetricValue],
    debt: _Observation,
    risk_free: _Observation,
) -> tuple[float, float, bool, str]:
    interest = _metric_observation(values.get("interest_expense"))
    if interest.value is not None and debt.value is not None and debt.value > 0:
        estimate = _bounded_debt_rate(abs(interest.value) / debt.value)
        confidence = max(0.0, (interest.confidence + debt.confidence) / 2.0 - 0.15)
        return estimate, confidence, True, "Despesa de juros / divida final; proxy historica, nao yield marginal"
    fallback = _bounded_debt_rate(risk_free.value + MARKET.default_credit_spread)
    return fallback, confidence_for_source("fallback"), True, "Taxa livre de risco + spread de credito padrao de config.py"


def _capital_confidence(
    equity: _Observation,
    debt: _Observation,
    ke_confidence: float,
    debt_cost_confidence: float,
    tax_confidence: float,
    equity_weight: float,
    debt_weight: float,
) -> float:
    financing_confidence = ke_confidence * equity_weight
    if debt_weight > 0:
        financing_confidence += ((debt_cost_confidence + tax_confidence) / 2.0) * debt_weight
    weights_confidence = (equity.confidence + debt.confidence) / 2.0
    return clamp(financing_confidence * 0.75 + weights_confidence * 0.25, 0.0, 1.0)


def _average_confidence(*observations: _Observation) -> float:
    available = [item.confidence for item in observations if item.value is not None]
    return sum(available) / len(available) if available else 0.0


def _bounded_rate(value: float) -> float:
    return clamp(value, MARKET.min_discount_rate, MARKET.max_discount_rate)


def _bounded_debt_rate(value: float) -> float:
    return clamp(value, 0.0, MARKET.max_pre_tax_cost_of_debt)
