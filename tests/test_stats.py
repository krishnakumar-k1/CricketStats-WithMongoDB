import math

import pytest

from cricketstats.stats import batting_average


def test_batting_average() -> None:
    assert batting_average(runs=245, dismissals=5) == 49.0


def test_batting_average_not_out() -> None:
    assert math.isinf(batting_average(runs=100, dismissals=0))


def test_batting_average_rejects_negative_dismissals() -> None:
    with pytest.raises(ValueError):
        batting_average(runs=100, dismissals=-1)
