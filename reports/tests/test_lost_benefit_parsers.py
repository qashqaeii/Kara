"""Unit tests for LostBenefitSeparate / monthly group benefit parsers."""

from decimal import Decimal

from reports.services.parsers.lost_benefit import (
    group_benefit_ranking,
    monthly_group_benefit_series,
    product_profit_ranking,
)


def test_product_profit_ranking_aggregates_by_stuff_code():
    rows = [
        {
            "StuffCode": "50000900",
            "StuffName": "تن ماهی",
            "StuffGroupName": "کنسرو",
            "SalePrice": "42,000,000",
            "BuyPrice": "38,400,000",
            "BenefitLostPrice": "3,600,000",
        },
        {
            "StuffCode": "50000900",
            "StuffName": "تن ماهی",
            "StuffGroupName": "کنسرو",
            "SalePrice": "10,000,000",
            "BuyPrice": "8,000,000",
            "BenefitLostPrice": "2,000,000",
        },
        {
            "StuffCode": "50003000",
            "StuffName": "کلوچه",
            "StuffGroupName": "کیک",
            "SalePrice": "12,500,000",
            "BuyPrice": "8,800,000",
            "BenefitLostPrice": "3,700,000",
        },
        {
            "StuffCode": "X",
            "StuffName": "صفر",
            "SalePrice": "0",
            "BuyPrice": "0",
            "BenefitLostPrice": "0",
        },
    ]
    ranked = product_profit_ranking(rows, limit=5)
    assert len(ranked) == 2
    assert ranked[0]["code"] == "50000900"
    assert ranked[0]["benefit_amount"] == 5_600_000.0
    assert ranked[1]["code"] == "50003000"
    assert ranked[0]["margin_percent"] > 0


def test_monthly_group_benefit_series_sums_months():
    rows = [
        {"StuffGroupName": "A", "TotalBenefit": "100", "Benefit1": "10", "Benefit5": "40"},
        {"StuffGroupName": "B", "TotalBenefit": "50", "Benefit1": "5", "Benefit5": "20"},
    ]
    series = monthly_group_benefit_series(rows)
    assert series["available"] is True
    assert series["series"][0]["amount"] == 15.0  # Farvardin
    assert series["series"][4]["amount"] == 60.0  # Mordad
    assert series["total"] == 75.0


def test_group_benefit_ranking():
    rows = [
        {"StuffGroupName": "کیک", "StuffSubGroupName": "کلوچه", "TotalBenefit": "24,652,524"},
        {"StuffGroupName": "کیک", "StuffSubGroupName": "کیک", "TotalBenefit": "10,000,000"},
        {"StuffGroupName": "نوشیدنی", "StuffSubGroupName": "", "TotalBenefit": "0"},
    ]
    ranked = group_benefit_ranking(rows, limit=5)
    assert len(ranked) == 2
    assert ranked[0]["benefit_amount"] == 24_652_524.0
