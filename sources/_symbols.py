"""Board/exchange resolution from a six-digit A-share code.

Kept in one place because every source encodes the exchange differently and
getting Beijing wrong is the most common way these adapters silently return
nothing: BJ codes fall through a naive "starts with 6 -> Shanghai, else
Shenzhen" test and get requested from the wrong exchange, which answers with an
empty payload rather than an error.
"""

SHANGHAI = ("60", "68", "90", "ii")   # main board, STAR, B-shares
SHENZHEN = ("00", "30", "20")         # main board, ChiNext, B-shares
BEIJING = ("43", "83", "87", "88", "92")


def exchange(symbol: str) -> str:
    """Return 'SH', 'SZ' or 'BJ'. Raises on anything unrecognised."""
    s = symbol.strip()
    if len(s) != 6 or not s.isdigit():
        raise ValueError(f"not a six-digit A-share code: {symbol!r}")
    if s.startswith(SHANGHAI):
        return "SH"
    if s.startswith(SHENZHEN):
        return "SZ"
    if s.startswith(BEIJING):
        return "BJ"
    raise ValueError(f"unrecognised board for {symbol!r}")


def tushare_code(symbol: str) -> str:
    return f"{symbol}.{exchange(symbol)}"


def eastmoney_secid(symbol: str) -> str:
    # 1 = Shanghai, 0 = Shenzhen and Beijing.
    return f"{'1' if exchange(symbol) == 'SH' else '0'}.{symbol}"


def sina_symbol(symbol: str) -> str:
    return {"SH": "sh", "SZ": "sz", "BJ": "bj"}[exchange(symbol)] + symbol
