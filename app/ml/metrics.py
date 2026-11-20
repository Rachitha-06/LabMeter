"""Error metrics for forecasts. Each pair is (predicted, actual)."""
from __future__ import annotations

import math
from typing import Sequence, Tuple

Pair = Tuple[float, float]


def _check(pairs: Sequence[Pair]) -> None:
    if not pairs:
        raise ValueError("no paired values to score")
    for predicted, actual in pairs:
        if not (math.isfinite(predicted) and math.isfinite(actual)):
            raise ValueError("non-finite values cannot be scored")


def mae(pairs: Sequence[Pair]) -> float:
    """Mean absolute error: the average size of a miss, in the same units as the data (kWh)."""
    _check(pairs)
    return sum(abs(p - a) for p, a in pairs) / len(pairs)


def rmse(pairs: Sequence[Pair]) -> float:
    """Root mean squared error: like MAE, but large misses count more heavily."""
    _check(pairs)
    return math.sqrt(sum((p - a) ** 2 for p, a in pairs) / len(pairs))
