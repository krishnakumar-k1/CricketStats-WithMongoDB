def batting_average(runs: int, dismissals: int) -> float:
    """Return batting average as runs divided by dismissals."""
    if dismissals < 0:
        raise ValueError("dismissals must be zero or positive")
    if dismissals == 0:
        return float("inf")
    return runs / dismissals
