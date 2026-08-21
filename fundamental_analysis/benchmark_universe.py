"""Curated benchmark universe used to diagnose score behavior.

The groups are calibration strata, not immutable company classifications. A
company can migrate between strata as its economics change, especially the
negative-FCF and early-growth watchlist.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class BenchmarkCase:
    ticker: str
    benchmark_group: str
    sector_bucket: str
    rationale: str


DEFAULT_BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase("MLI", "tradicionais_ciclicas", "metal_fabrication", "Industrial de nicho com geracao de caixa e ciclo economico."),
    BenchmarkCase("NUE", "tradicionais_ciclicas", "steel", "Siderurgia ciclica e intensiva em capital."),
    BenchmarkCase("CAT", "tradicionais_ciclicas", "industrial_machinery", "Bens de capital com ciclo e base instalada."),
    BenchmarkCase("DE", "tradicionais_ciclicas", "agricultural_machinery", "Maquinas agricolas e exposicao ao ciclo de commodities."),
    BenchmarkCase("HON", "tradicionais_ciclicas", "industrial_conglomerate", "Industrial diversificada com margens maduras."),
    BenchmarkCase("EMR", "tradicionais_ciclicas", "industrial_automation", "Automacao industrial e receitas recorrentes de servicos."),
    BenchmarkCase("ETN", "tradicionais_ciclicas", "electrical_equipment", "Eletrificacao industrial com crescimento e capital fisico."),
    BenchmarkCase("PH", "tradicionais_ciclicas", "motion_control", "Componentes industriais diversificados."),
    BenchmarkCase("F", "tradicionais_ciclicas", "auto_manufacturers", "Montadora madura, ciclica e intensiva em capital."),
    BenchmarkCase("GM", "tradicionais_ciclicas", "auto_manufacturers", "Montadora madura com financeira cativa."),
    BenchmarkCase("MSFT", "growth_tech", "software", "Software de escala, nuvem e receitas recorrentes."),
    BenchmarkCase("AAPL", "growth_tech", "consumer_technology", "Ecossistema de hardware, servicos e forte conversao de caixa."),
    BenchmarkCase("GOOGL", "growth_tech", "digital_advertising", "Plataformas digitais com investimento elevado em tecnologia."),
    BenchmarkCase("META", "growth_tech", "digital_advertising", "Plataforma digital com margens altas e reinvestimento."),
    BenchmarkCase("AMZN", "growth_tech", "commerce_cloud", "Comercio de margem baixa combinado com nuvem de margem alta."),
    BenchmarkCase("NVDA", "growth_tech", "semiconductor", "Semicondutores de alto crescimento e ciclo tecnologico."),
    BenchmarkCase("AVGO", "growth_tech", "semiconductor_software", "Semicondutores e software de infraestrutura."),
    BenchmarkCase("CRM", "growth_tech", "software", "Software corporativo recorrente em fase de maturacao."),
    BenchmarkCase("ADBE", "growth_tech", "software", "Software criativo recorrente e alto retorno sobre capital."),
    BenchmarkCase("NOW", "growth_tech", "software", "Software corporativo com crescimento e multiplo elevado."),
    BenchmarkCase("JPM", "bancos_financeiras", "diversified_bank", "Banco universal diversificado."),
    BenchmarkCase("BAC", "bancos_financeiras", "diversified_bank", "Banco universal sensivel a juros e credito."),
    BenchmarkCase("WFC", "bancos_financeiras", "diversified_bank", "Banco universal com foco domestico."),
    BenchmarkCase("C", "bancos_financeiras", "diversified_bank", "Banco global em reestruturacao."),
    BenchmarkCase("GS", "bancos_financeiras", "capital_markets", "Banco de investimento e gestao de ativos."),
    BenchmarkCase("MS", "bancos_financeiras", "capital_markets", "Wealth management e banco de investimento."),
    BenchmarkCase("USB", "bancos_financeiras", "regional_bank", "Banco regional de grande porte."),
    BenchmarkCase("PNC", "bancos_financeiras", "regional_bank", "Banco regional diversificado."),
    BenchmarkCase("TFC", "bancos_financeiras", "regional_bank", "Banco regional com risco de credito e depositos."),
    BenchmarkCase("BK", "bancos_financeiras", "custody_bank", "Custodia e servicos financeiros baseados em tarifas."),
    BenchmarkCase("RIVN", "fcf_negativo_early_growth", "electric_vehicles", "Caso de estresse: escala industrial e queima de caixa devem ser confirmadas na data-base."),
    BenchmarkCase("LCID", "fcf_negativo_early_growth", "electric_vehicles", "Caso de estresse: demanda, financiamento e runway devem ser confirmados na data-base."),
    BenchmarkCase("RKLB", "fcf_negativo_early_growth", "aerospace", "Empresa em expansao com capex e risco de execucao."),
    BenchmarkCase("JOBY", "fcf_negativo_early_growth", "advanced_mobility", "Empresa pre-receita relevante e dependente de certificacao."),
    BenchmarkCase("ACHR", "fcf_negativo_early_growth", "advanced_mobility", "Empresa pre-escala com risco tecnologico e regulatorio."),
    BenchmarkCase("IONQ", "fcf_negativo_early_growth", "quantum_computing", "Tecnologia emergente com monetizacao ainda em formacao."),
    BenchmarkCase("CRSP", "fcf_negativo_early_growth", "biotechnology", "Biotecnologia dependente de pipeline e marcos clinicos."),
    BenchmarkCase("BEAM", "fcf_negativo_early_growth", "biotechnology", "Biotecnologia pre-lucro com risco binario de pipeline."),
    BenchmarkCase("RXRX", "fcf_negativo_early_growth", "biotechnology", "Descoberta de farmacos baseada em tecnologia e alto consumo de caixa."),
    BenchmarkCase("SNOW", "fcf_negativo_early_growth", "software", "Growth software; o perfil de FCF deve ser revalidado em cada data-base."),
)


def validate_benchmark_cases(
    cases: Iterable[BenchmarkCase] = DEFAULT_BENCHMARK_CASES,
    minimum_per_group: int = 1,
) -> None:
    cases = tuple(cases)
    tickers = [case.ticker.upper().strip() for case in cases]
    duplicates = sorted(ticker for ticker, count in Counter(tickers).items() if count > 1)
    if duplicates:
        raise ValueError(f"Tickers duplicados no benchmark: {', '.join(duplicates)}")
    if any(not ticker for ticker in tickers):
        raise ValueError("O universo de benchmark contem ticker vazio")
    group_counts = benchmark_group_counts(cases)
    undersized = sorted(group for group, count in group_counts.items() if count < minimum_per_group)
    if undersized:
        raise ValueError(f"Grupos abaixo da amostra minima: {', '.join(undersized)}")


def benchmark_group_counts(
    cases: Iterable[BenchmarkCase] = DEFAULT_BENCHMARK_CASES,
) -> dict[str, int]:
    return dict(Counter(case.benchmark_group for case in cases))


def benchmark_tickers(
    cases: Iterable[BenchmarkCase] = DEFAULT_BENCHMARK_CASES,
) -> list[str]:
    cases = tuple(cases)
    validate_benchmark_cases(cases)
    return [case.ticker for case in cases]

