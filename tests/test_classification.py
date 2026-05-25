from investment_forecasting.data.classification import classify_asset_theme


def test_classifies_common_asset_themes_from_names_and_types():
    assert classify_asset_theme(name="科技成长股票", asset_type="fund")["key"] == "technology"
    assert classify_asset_theme(name="国债ETF", asset_type="etf")["key"] == "fixed_income"
    assert classify_asset_theme(name="贵州茅台", asset_type="stock")["key"] == "consumer"
    assert classify_asset_theme(name="沪深300", asset_type="index")["key"] == "broad_market"


def test_unknown_theme_keeps_auditable_reason():
    result = classify_asset_theme(name="资料待补基金", asset_type="fund")

    assert result["key"] == "unknown"
    assert "缺少可识别主题关键词" in result["reason"]
