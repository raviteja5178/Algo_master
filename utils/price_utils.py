"""
Price / tick-size utilities.
"""


def round_to_tick(price: float, tick_size: float = 0.05) -> float:
    """Round price to the nearest valid tick size."""
    return round(round(price / tick_size) * tick_size, 2)


def clamp_min(value: float, minimum: float) -> float:
    """Ensure value never goes below minimum (used for stop enforcement)."""
    return max(value, minimum)
