"""Catálogo de planos e regras comerciais do NutriOS-AI.

Este módulo é deliberadamente puro: não acessa banco nem gateway de pagamento.
Isso permite testar as regras de negócio antes de conectar cobrança real.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PlanCode = Literal["trial", "essencial", "profissional", "premium"]


@dataclass(frozen=True)
class Plan:
    code: PlanCode
    name: str
    monthly_brl: int
    patient_limit: int | None
    ai_messages_monthly: int | None
    custom_branding: bool
    custom_domain: bool
    team_members: int


PLANS: dict[PlanCode, Plan] = {
    "trial": Plan("trial", "Teste grátis", 0, 10, 100, True, False, 1),
    "essencial": Plan("essencial", "Essencial", 79, 100, 500, True, False, 1),
    "profissional": Plan("profissional", "Profissional", 149, 500, 2000, True, True, 3),
    "premium": Plan("premium", "Premium", 299, None, None, True, True, 10),
}

TRIAL_DAYS = 14


def get_plan(code: str) -> Plan:
    try:
        return PLANS[code.lower().strip()]  # type: ignore[index]
    except KeyError as exc:
        raise ValueError(f"Plano inválido: {code}") from exc


def within_limit(value: int, limit: int | None) -> bool:
    return limit is None or value < limit


def feature_enabled(code: str, feature: str) -> bool:
    plan = get_plan(code)
    return {
        "custom_branding": plan.custom_branding,
        "custom_domain": plan.custom_domain,
        "team": plan.team_members > 1,
    }.get(feature, False)
