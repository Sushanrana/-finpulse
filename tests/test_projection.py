"""Feature 7: Opportunity Cost Time Machine."""
import json
import re

import pytest

from services import projection
from services.validation import ValidationError


def test_future_value_matches_formula():
    # P=100, 7% p.a., 10 years: i=0.07/12, n=120
    i = 0.07 / 12
    expected = 100 * (((1 + i) ** 120 - 1) / i)
    assert projection.future_value(100, 7, 10) == pytest.approx(expected)
    assert projection.future_value(100, 7, 10) == pytest.approx(17308.48, abs=0.01)


def test_zero_rate_is_simple_sum():
    assert projection.future_value(250, 0, 5) == 250 * 60


def test_compare_horizons_and_chart():
    result = projection.compare(200, 8)
    years = [h["years"] for h in result["horizons"]]
    assert years == [5, 10, 20]
    h20 = result["horizons"][2]
    assert h20["spent"] == 48000
    assert h20["invested"] == pytest.approx(projection.future_value(200, 8, 20), abs=0.01)
    assert h20["growth"] > 0
    assert len(result["chart"]["labels"]) == 21 and result["chart"]["invested"][0] == 0


@pytest.mark.parametrize("monthly,rate", [("-5", "7"), ("abc", "7"), ("0", "7"), ("100", "31"), ("100", "-1"), ("200000", "5")])
def test_input_validation(monthly, rate):
    with pytest.raises(ValidationError):
        projection.validate_inputs(monthly, rate)


def test_time_machine_page(alice):
    resp = alice.get("/time-machine?monthly=100&rate=7")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "A$17,308.48" in body  # 10-year value
    data = json.loads(re.search(r'id="time-machine-data">(.*?)</script>', body, re.S).group(1))
    assert data["spent"][10] == 12000


def test_time_machine_invalid_input(alice):
    resp = alice.get("/time-machine?monthly=<script>&rate=99")
    assert resp.status_code == 400
    assert "<script>" not in resp.get_data(as_text=True)
