from app.modules.tariff.services.tariff_service import TariffService


def test_tariff_context_uses_reference_average_policy():
    result = TariffService().get_context()

    assert result.available is True
    assert result.current.price_per_kwh == 0.54
    assert result.current.currency == "CNY"
    assert result.current.period is None
    assert result.source.provider == "NDRC"
    assert result.source.pricing_type == "reference_average"
    assert result.source.region == "CN"
    assert result.source.reference_date == "2019-08-23"
    assert result.source.realtime is False
    assert result.observed_at is not None


def test_tariff_value_is_loaded_from_yaml_policy():
    policy = TariffService.load_policy()

    assert policy.reference.price_per_kwh == 0.54
    assert policy.reference.realtime is False
    assert policy.unit == "kWh"
