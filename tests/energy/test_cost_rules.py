from datetime import date
from decimal import Decimal

from app.services.energy_costs import (
    ALL_WEEKDAYS, BandSpec, FactorSpec, bands_overlap, estimate, factor_for, format_weekdays, parse_weekdays, rate_for,
)

D = Decimal
MON = date(2026, 10, 5)   # Monday
SAT = date(2026, 10, 10)  # Saturday


def band(rate, start, end, weekdays=ALL_WEEKDAYS, effective_from=date(2026, 1, 1), effective_to=None):
    return BandSpec(rate_per_kwh=D(rate), currency="INR", effective_from=effective_from, effective_to=effective_to,
                    weekdays=frozenset(weekdays), start_hour=start, end_hour=end)


PEAK = band("12", 9, 17, weekdays=range(5))
NIGHT = band("6", 0, 9, weekdays=range(5))
EVENING = band("6", 17, 24, weekdays=range(5))
WEEKEND = band("6", 0, 24, weekdays=(5, 6))
TIME_OF_USE = [PEAK, NIGHT, EVENING, WEEKEND]


def test_peak_rate_applies_inside_its_hours_only():
    assert rate_for(TIME_OF_USE, MON, 9) == D("12")
    assert rate_for(TIME_OF_USE, MON, 16) == D("12")
    assert rate_for(TIME_OF_USE, MON, 17) == D("6")  # end hour is exclusive


def test_weekend_uses_the_weekend_band_and_weekdays_do_not():
    assert rate_for(TIME_OF_USE, SAT, 10) == D("6")
    assert rate_for(TIME_OF_USE, MON, 3) == D("6")


def test_an_hour_with_no_covering_band_has_no_rate():
    assert rate_for([PEAK], MON, 3) is None


def test_bands_are_active_only_within_their_dates():
    expired = band("9", 0, 24, effective_from=date(2025, 1, 1), effective_to=date(2025, 12, 31))
    assert rate_for([expired], MON, 10) is None


def test_overlapping_bands_are_detected_by_date_weekday_and_hour():
    assert bands_overlap(PEAK, band("7", 12, 14, weekdays=range(5)))
    assert not bands_overlap(PEAK, WEEKEND)                       # different weekdays
    assert not bands_overlap(PEAK, NIGHT)                         # touching hours only
    assert not bands_overlap(band("1", 0, 24, effective_from=date(2025, 1, 1), effective_to=date(2025, 12, 31)), PEAK)


def test_weekday_text_round_trips_and_all_days_is_stored_as_none():
    assert format_weekdays(range(7)) is None
    assert format_weekdays([4, 0, 2]) == "0,2,4"
    assert parse_weekdays("0,2,4") == frozenset({0, 2, 4})
    assert parse_weekdays(None) == ALL_WEEKDAYS


def test_emission_factor_is_chosen_by_the_day_it_applies_to():
    factors = [FactorSpec(D("0.8"), "kgCO2e/kWh", date(2026, 1, 1), date(2026, 6, 30), "test"),
               FactorSpec(D("0.6"), "kgCO2e/kWh", date(2026, 7, 1), None, "test")]
    assert factor_for(factors, date(2026, 6, 30)).value == D("0.8")
    assert factor_for(factors, date(2026, 7, 1)).value == D("0.6")
    assert factor_for(factors, date(2025, 12, 31)) is None


def test_cost_and_emissions_are_exact_sums_of_hourly_products():
    hours = [
        (MON, 10, D("2.0"), "measured"),   # peak: 2.0 x 12 = 24.00
        (MON, 3, D("1.0"), "measured"),    # night: 1.0 x 6 = 6.00
        (SAT, 3, D("0.5"), "simulated"),   # weekend: 0.5 x 6 = 3.00
        (MON, 19, D("1.5"), "measured"),   # evening: 1.5 x 6 = 9.00
    ]
    factors = [FactorSpec(D("0.5"), "kgCO2e/kWh", date(2026, 1, 1), None, "test")]
    per_day = estimate(hours, TIME_OF_USE, factors)
    assert per_day[MON].cost == D("39.0000")
    assert per_day[SAT].cost == D("3.0000")
    total_cost = sum(d.cost for d in per_day.values())
    total_kwh = sum(d.kwh for d in per_day.values())
    assert total_cost == D("42.0000") and total_kwh == D("5.0")
    assert per_day[SAT].kwh_by_type == {"simulated": D("0.5")}
    assert sum(d.emissions for d in per_day.values()) == D("2.5000")


def test_hours_without_a_band_or_factor_are_counted_not_guessed():
    hours = [(MON, 3, D("1.0"), "measured")]
    per_day = estimate(hours, [PEAK], [])
    entry = per_day[MON]
    assert entry.cost == D("0") and entry.kwh_uncosted == D("1.0") and entry.kwh_costed == D("0")
    assert entry.emissions == D("0") and entry.kwh_unfactored == D("1.0")
