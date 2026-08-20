"""Known NSE sector mapping for common holdings (expand over time)."""

SECTOR_MAP: dict[str, str] = {
    "RELIANCE": "Energy",
    "HDFCBANK": "Financials",
    "HDFC": "Financials",
    "ICICIBANK": "Financials",
    "SBIN": "Financials",
    "KOTAKBANK": "Financials",
    "AXISBANK": "Financials",
    "TCS": "IT",
    "INFY": "IT",
    "WIPRO": "IT",
    "HCLTECH": "IT",
    "TECHM": "IT",
    "SWIGGY": "Consumer",
    "ETERNAL": "Consumer",
    "VBL": "Consumer",
    "TATAPOWER": "Utilities",
    "NTPC": "Utilities",
    "POWERGRID": "Utilities",
    "ITC": "Consumer",
    "HINDUNILVR": "Consumer",
    "BHARTIARTL": "Telecom",
    "SUNPHARMA": "Healthcare",
    "DRREDDY": "Healthcare",
    "MARUTI": "Auto",
    "TATAMOTORS": "Auto",
    "ASIANPAINT": "Materials",
    "LT": "Industrials",
}

# Research candidates when a sector is underweight (education only, not advice)
SECTOR_CANDIDATES: dict[str, list[str]] = {
    "IT": ["TCS", "INFY"],
    "Healthcare": ["SUNPHARMA", "DRREDDY"],
    "Auto": ["MARUTI", "M&M"],
    "Industrials": ["LT", "HAL"],
    "Materials": ["ASIANPAINT", "ULTRACEMCO"],
}

CORE_DIVERSIFIERS = [
    {
        "name": "Nifty 50 Index Fund / ETF",
        "reason": "Core Indian equity exposure with instant diversification across 50 large caps.",
        "type": "index_fund",
    },
    {
        "name": "Flexi-cap Mutual Fund",
        "reason": "Professional management across market caps when direct stock picking is concentrated.",
        "type": "mutual_fund",
    },
]
