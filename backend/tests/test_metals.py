import pytest

from app import metals


def test_convert_between_currencies():
    assert metals.convert(90, "EUR", "USD") == pytest.approx(100)
    assert metals.convert(100, "USD", "CHF") == pytest.approx(80)
    assert metals.convert(None, "EUR", "USD") is None


def test_melt_value_gold_10_francs():
    # 10 Francs Napoléon: 3.2258 g at 900/1000
    melt = metals.melt_value("gold", 3.2258, 0.9, "USD")
    assert melt["pure_metal_g"] == pytest.approx(2.903, abs=1e-3)
    assert melt["value"] == pytest.approx(2.90322 * 4000 / metals.TROY_OZ_G, abs=0.01)


def test_melt_value_billon_priced_as_silver():
    assert metals.melt_value("billon", 10, 0.2, "USD")["metal"] == "silver"


@pytest.mark.parametrize("metal,weight,fineness", [("copper", 5, 0.95), ("gold", None, 0.9), ("gold", 3, None)])
def test_melt_value_none_when_not_computable(metal, weight, fineness):
    assert metals.melt_value(metal, weight, fineness, "EUR") is None
