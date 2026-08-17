"""Contratos simples para evitar regressões na fronteira multi-tenant.

A integração real com Supabase/gateway deve acrescentar testes de integração.
"""
from app.saas_plans import get_plan


def test_paid_features_are_not_assumed_for_trial():
    trial = get_plan("trial")
    assert trial.custom_domain is False
    assert trial.team_members == 1


def test_premium_has_no_artificial_patient_limit():
    assert get_plan("premium").patient_limit is None
