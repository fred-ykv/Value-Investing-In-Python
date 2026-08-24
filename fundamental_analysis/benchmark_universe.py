"""Curated benchmark universe used to diagnose score behavior.

The groups are calibration strata, not immutable company classifications. A
company can migrate between strata as its economics change, especially the
negative-FCF and early-growth watchlist.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Iterable


@dataclass(frozen=True)
class HistoricalLifecycleEvent:
    event_type: str
    effective_date: date
    terminal_value_per_share: float
    source_url: str
    accession_number: str
    event_date_source_url: str = ""


@dataclass(frozen=True)
class BenchmarkCase:
    ticker: str
    benchmark_group: str
    sector_bucket: str
    rationale: str
    is_cyclical: bool = False
    cik: str = ""
    universe_status: str = "active"
    lifecycle_event: HistoricalLifecycleEvent | None = None


DEFAULT_BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase("MLI", "tradicionais_ciclicas", "metal_fabrication", "Industrial de nicho com geracao de caixa e ciclo economico.", True),
    BenchmarkCase("NUE", "tradicionais_ciclicas", "steel", "Siderurgia ciclica e intensiva em capital.", True),
    BenchmarkCase("CAT", "tradicionais_ciclicas", "industrial_machinery", "Bens de capital com ciclo e base instalada.", True),
    BenchmarkCase("DE", "tradicionais_ciclicas", "agricultural_machinery", "Maquinas agricolas e exposicao ao ciclo de commodities.", True),
    BenchmarkCase("HON", "tradicionais_ciclicas", "industrial_conglomerate", "Industrial diversificada com margens maduras."),
    BenchmarkCase("EMR", "tradicionais_ciclicas", "industrial_automation", "Automacao industrial e receitas recorrentes de servicos."),
    BenchmarkCase("ETN", "tradicionais_ciclicas", "electrical_equipment", "Eletrificacao industrial com crescimento e capital fisico."),
    BenchmarkCase("PH", "tradicionais_ciclicas", "motion_control", "Componentes industriais diversificados."),
    BenchmarkCase("F", "tradicionais_ciclicas", "auto_manufacturers", "Montadora madura, ciclica e intensiva em capital.", True),
    BenchmarkCase("GM", "tradicionais_ciclicas", "auto_manufacturers", "Montadora madura com financeira cativa.", True),
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
    BenchmarkCase("BNY", "bancos_financeiras", "custody_bank", "Custodia e servicos financeiros baseados em tarifas."),
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


HISTORICAL_LIFECYCLE_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        "MDLA",
        "fcf_negativo_early_growth",
        "experience_management_software",
        "SaaS de experiencia adquirido apos periodo de alto crescimento e consumo de caixa.",
        cik="0001540184",
        universe_status="acquired",
        lifecycle_event=HistoricalLifecycleEvent(
            "cash_acquisition",
            date(2021, 10, 29),
            34.00,
            "https://www.sec.gov/Archives/edgar/data/1540184/000114036121036202/brhc10030210_8k.htm",
            "0001140361-21-036202",
        ),
    ),
    BenchmarkCase(
        "CLDR",
        "fcf_negativo_early_growth",
        "data_platform_software",
        "Plataforma de dados retirada da bolsa durante transicao para receitas recorrentes.",
        cik="0001535379",
        universe_status="acquired",
        lifecycle_event=HistoricalLifecycleEvent(
            "cash_acquisition",
            date(2021, 10, 8),
            16.00,
            "https://www.sec.gov/Archives/edgar/data/1535379/000119312521294924/d223205d8k.htm",
            "0001193125-21-294924",
        ),
    ),
    BenchmarkCase(
        "CSPR",
        "fcf_negativo_early_growth",
        "direct_to_consumer",
        "Empresa digital de consumo adquirida apos IPO, perdas operacionais e baixa escala.",
        cik="0001598674",
        universe_status="acquired",
        lifecycle_event=HistoricalLifecycleEvent(
            "cash_acquisition",
            date(2022, 1, 25),
            6.90,
            "https://www.sec.gov/Archives/edgar/data/1598674/000114036122002541/brhc10033043_ex99-1.htm",
            "0001140361-22-002541",
        ),
    ),
    BenchmarkCase(
        "PLAN",
        "fcf_negativo_early_growth",
        "planning_software",
        "SaaS de planejamento adquirido durante correcao de multiplos de growth.",
        cik="0001540755",
        universe_status="acquired",
        lifecycle_event=HistoricalLifecycleEvent(
            "cash_acquisition",
            date(2022, 6, 22),
            63.75,
            "https://www.sec.gov/Archives/edgar/data/1540755/000119312522178282/d333986d8k.htm",
            "0001193125-22-178282",
        ),
    ),
    BenchmarkCase(
        "ZEN",
        "growth_tech",
        "customer_service_software",
        "SaaS de atendimento adquirido depois de desaceleracao e revisao estrategica.",
        cik="0001463172",
        universe_status="acquired",
        lifecycle_event=HistoricalLifecycleEvent(
            "cash_acquisition",
            date(2022, 11, 22),
            77.50,
            "https://www.sec.gov/Archives/edgar/data/1463172/000114036122042681/brhc10044488_8k.htm",
            "0001140361-22-042681",
        ),
    ),
    BenchmarkCase(
        "COUP",
        "fcf_negativo_early_growth",
        "spend_management_software",
        "SaaS de gestao de gastos adquirido apos forte compressao de valuation.",
        cik="0001385867",
        universe_status="acquired",
        lifecycle_event=HistoricalLifecycleEvent(
            "cash_acquisition",
            date(2023, 2, 28),
            81.00,
            "https://www.sec.gov/Archives/edgar/data/1385867/000119312523054081/d455192d8k.htm",
            "0001193125-23-054081",
        ),
    ),
    BenchmarkCase(
        "MNTV",
        "fcf_negativo_early_growth",
        "survey_software",
        "Software de pesquisas adquirido depois de rebranding e deterioracao de valor.",
        cik="0001739936",
        universe_status="acquired",
        lifecycle_event=HistoricalLifecycleEvent(
            "cash_acquisition",
            date(2023, 5, 31),
            9.46,
            "https://www.sec.gov/Archives/edgar/data/1739936/000114036123027837/ny20009286x1_8k.htm",
            "0001140361-23-027837",
        ),
    ),
    BenchmarkCase(
        "XM",
        "fcf_negativo_early_growth",
        "experience_management_software",
        "SaaS de experiencia adquirido pouco depois do carve-out e IPO.",
        cik="0001747748",
        universe_status="acquired",
        lifecycle_event=HistoricalLifecycleEvent(
            "cash_acquisition",
            date(2023, 6, 28),
            18.15,
            "https://www.sec.gov/Archives/edgar/data/1747748/000162828023023743/xm-20230628.htm",
            "0001628280-23-023743",
        ),
    ),
    BenchmarkCase(
        "BBBY",
        "tradicionais_ciclicas",
        "specialty_retail",
        "Varejista liquidada no Chapter 11; as acoes foram canceladas sem recuperacao.",
        cik="0000886158",
        universe_status="bankrupt_cancelled",
        lifecycle_event=HistoricalLifecycleEvent(
            "cancelled_zero",
            date(2023, 9, 29),
            0.0,
            "https://www.sec.gov/Archives/edgar/data/886158/000119312523238592/d521320dex21.htm",
            "0001193125-23-238592",
            "https://www.sec.gov/Archives/edgar/data/886158/000119312523247428/d579010dex991.htm",
        ),
    ),
    BenchmarkCase(
        "NEWR",
        "fcf_negativo_early_growth",
        "observability_software",
        "SaaS de observabilidade adquirido apos transicao de modelo comercial.",
        cik="0001448056",
        universe_status="acquired",
        lifecycle_event=HistoricalLifecycleEvent(
            "cash_acquisition",
            date(2023, 11, 8),
            87.00,
            "https://www.sec.gov/Archives/edgar/data/1448056/000119312523273042/d469974d8k.htm",
            "0001193125-23-273042",
        ),
    ),
)


HISTORICAL_BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    *DEFAULT_BENCHMARK_CASES,
    *HISTORICAL_LIFECYCLE_CASES,
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
    for case in cases:
        if case.lifecycle_event is None:
            continue
        if not case.cik.isdigit() or len(case.cik) != 10:
            raise ValueError(f"CIK historico invalido para {case.ticker}: {case.cik}")
        event = case.lifecycle_event
        if event.event_type not in {"cash_acquisition", "cancelled_zero"}:
            raise ValueError(f"Evento historico invalido para {case.ticker}: {event.event_type}")
        if event.event_type == "cash_acquisition" and event.terminal_value_per_share <= 0:
            raise ValueError(f"Valor terminal de aquisicao invalido para {case.ticker}")
        if event.event_type == "cancelled_zero" and event.terminal_value_per_share != 0:
            raise ValueError(f"Cancelamento deve ter valor terminal zero para {case.ticker}")
        if "sec.gov/Archives/edgar/data/" not in event.source_url:
            raise ValueError(f"Fonte SEC ausente para o evento de {case.ticker}")
        if not event.accession_number:
            raise ValueError(f"Accession SEC ausente para o evento de {case.ticker}")
        if event.event_type == "cancelled_zero" and not event.event_date_source_url:
            raise ValueError(
                f"Fonte da data efetiva ausente para o cancelamento de {case.ticker}"
            )


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
