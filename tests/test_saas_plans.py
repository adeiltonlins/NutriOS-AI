from app.saas_plans import PLANS, feature_enabled, get_plan, within_limit


def test_all_public_plans_exist():
    assert {"trial", "essencial", "profissional", "premium"} <= set(PLANS)


def test_plan_pricing_and_limits():
    assert get_plan("essencial").monthly_brl == 79
    assert get_plan("profissional").patient_limit == 500
    assert get_plan("premium").patient_limit is None


def test_limit_behavior():
    assert within_limit(99, 100)
    assert not within_limit(100, 100)
    assert within_limit(100000, None)


def test_feature_matrix():
    assert feature_enabled("essencial", "custom_branding")
    assert not feature_enabled("essencial", "custom_domain")
    assert feature_enabled("profissional", "custom_domain")
    assert feature_enabled("premium", "team")


def test_invalid_plan_is_rejected():
    try:
        get_plan("enterprise")
    except ValueError:
        return
    raise AssertionError("invalid plan should raise ValueError")
