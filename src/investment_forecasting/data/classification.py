from __future__ import annotations

from typing import Any


THEME_LABELS = {
    "broad_market": "宽基/综合",
    "technology": "科技",
    "semiconductor": "半导体",
    "communication": "通信",
    "new_energy": "新能源",
    "consumer": "消费",
    "healthcare": "医药健康",
    "financial": "金融",
    "real_estate": "地产",
    "industrial": "工业制造",
    "materials": "周期材料",
    "energy": "能源",
    "defense": "军工",
    "agriculture": "农业",
    "overseas": "海外/QDII",
    "commodity": "商品",
    "fixed_income": "固收",
    "cash": "现金管理",
    "unknown": "主题待识别",
}


THEME_KEYWORDS = [
    ("cash", ("货币", "现金", "同业存单", "存单", "添利", "日利", "月月享")),
    ("fixed_income", ("债", "国债", "短债", "中短债", "纯债", "可转债", "固收", "信用债", "bond")),
    ("semiconductor", ("半导体", "芯片", "集成电路", "电子")),
    ("communication", ("通信", "5g", "信息技术", "传媒", "互联网", "云计算", "人工智能", "ai")),
    ("technology", ("科技", "计算机", "软件", "数字", "创新", "智能", "机器人")),
    ("new_energy", ("新能源", "光伏", "锂电", "电池", "电动车", "新能源汽车", "储能", "碳中和", "环保")),
    ("consumer", ("消费", "食品", "饮料", "白酒", "茅台", "家电", "旅游", "零售", "医美")),
    ("healthcare", ("医药", "医疗", "生物", "健康", "创新药", "中药", "疫苗")),
    ("financial", ("金融", "银行", "证券", "保险", "券商", "非银")),
    ("real_estate", ("地产", "房地产", "物业", "建筑")),
    ("defense", ("军工", "国防", "航天", "航空", "兵器")),
    ("energy", ("能源", "煤炭", "石油", "油气", "电力", "公用事业")),
    ("materials", ("钢铁", "有色", "化工", "材料", "资源", "稀土", "黄金", "金属")),
    ("agriculture", ("农业", "农林", "牧渔", "养殖", "种业")),
    ("industrial", ("制造", "机械", "高端装备", "装备", "工业", "汽车", "交通", "物流")),
    ("overseas", ("qdii", "港股", "恒生", "纳斯达克", "标普", "海外", "全球", "美股")),
    ("commodity", ("商品", "原油", "黄金", "白银", "豆粕", "有色商品")),
    ("broad_market", ("沪深300", "中证500", "中证1000", "创业板", "上证", "深证", "宽基", "指数")),
]


def classify_asset_theme(
    *,
    code: Any = None,
    name: Any = None,
    asset_type: Any = None,
    fund_type: Any = None,
) -> dict[str, str]:
    text = _search_text(code, name, asset_type, fund_type)
    for key, keywords in THEME_KEYWORDS:
        matched = next((keyword for keyword in keywords if keyword.lower() in text), None)
        if matched:
            return {
                "key": key,
                "label": THEME_LABELS[key],
                "reason": f"名称/类型包含“{matched}”",
            }
    asset_type_text = str(asset_type or "").lower()
    if asset_type_text == "index":
        return {"key": "broad_market", "label": THEME_LABELS["broad_market"], "reason": "市场指数默认归入宽基/综合"}
    return {"key": "unknown", "label": THEME_LABELS["unknown"], "reason": "名称和类型缺少可识别主题关键词"}


def theme_options() -> list[dict[str, str]]:
    return [{"key": key, "label": label} for key, label in THEME_LABELS.items() if key != "unknown"]


def _search_text(*values: Any) -> str:
    return " ".join(str(value or "").lower() for value in values)
