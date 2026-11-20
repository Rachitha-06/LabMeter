

import generate_synthetic_data as gen  # noqa: F401  (keeps the generator importable for shared fixtures)

PEAK = {"rate_per_kwh": "12.0000", "currency": "INR", "effective_from": "2026-01-01", "weekdays": [0, 1, 2, 3, 4],
        "start_hour": 9, "end_hour": 17, "time_band": "peak", "source": "test value: peak band"}
NIGHT = {**PEAK, "rate_per_kwh": "6.0000", "start_hour": 0, "end_hour": 9, "time_band": "night", "source": "test value: night"}
EVENING = {**PEAK, "rate_per_kwh": "6.0000", "start_hour": 17, "end_hour": 24, "time_band": "evening",
           "source": "test value: evening"}
WEEKEND = {"rate_per_kwh": "6.0000", "currency": "INR", "effective_from": "2026-01-01", "weekdays": [5, 6],
           "start_hour": 0, "end_hour": 24, "time_band": "weekend", "source": "test value: weekend"}
FACTOR = {"value": "0.5000", "unit": "kgCO2e/kWh", "effective_from": "2026-01-01", "version_or_year": "test-2026",
          "source": "test value: placeholder factor"}


def add_all_bands(client):
    for band in (PEAK, NIGHT, EVENING, WEEKEND):
        assert client.post("/api/tariffs", json=band).status_code == 201


def reading(client, lab_id, timestamp, kwh, reading_type="measured"):
    response = client.post("/api/readings", json={"lab_id": lab_id, "timestamp": timestamp, "value": kwh,
                                                  "reading_type": reading_type, "source": "test"})
    assert response.status_code == 201, response.text


def estimate(client, lab_id=None, granularity="day"):
    params = {"start": "2026-10-03T00:00:00Z", "end": "2026-10-12T00:00:00Z", "granularity": granularity}
    if lab_id is not None:
        params["lab_id"] = lab_id
    return client.get("/api/estimates/cost-emissions", params=params)


def test_no_tariff_or_factor_means_no_estimate(client, make_lab):
    lab_id = make_lab()
    response = estimate(client, lab_id)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_tariff"
    client.post("/api/tariffs", json=PEAK)
    assert estimate(client, lab_id).json()["error"]["code"] == "no_emission_factor"


def test_tariff_bands_must_name_their_source_and_currency(client):
    assert client.post("/api/tariffs", json={**PEAK, "source": "x"}).status_code == 422
    assert client.post("/api/tariffs", json={**PEAK, "currency": "rupees"}).status_code == 422


def test_overlapping_tariff_band_is_refused(client):
    client.post("/api/tariffs", json=PEAK)
    response = client.post("/api/tariffs", json={**PEAK, "start_hour": 12, "end_hour": 20, "time_band": "clash"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "tariff_overlap"


def test_overlapping_factors_are_refused(client):
    client.post("/api/emission-factors", json=FACTOR)
    response = client.post("/api/emission-factors", json={**FACTOR, "effective_from": "2026-06-01",
                                                          "effective_to": "2026-06-30"})
    assert response.status_code == 409


def test_time_of_use_cost_and_emissions_match_hand_calculation(client, make_lab):
    lab_id = make_lab()
    add_all_bands(client)
    client.post("/api/emission-factors", json=FACTOR)
    reading(client, lab_id, "2026-10-05T10:30:00+05:30", "2.0")   # Monday peak        2.0 x 12 = 24.00
    reading(client, lab_id, "2026-10-05T03:30:00+05:30", "1.0")   # Monday night       1.0 x 6  =  6.00
    reading(client, lab_id, "2026-10-10T03:30:00+05:30", "0.5", "simulated")  # Saturday  0.5 x 6 = 3.00
    reading(client, lab_id, "2026-10-05T19:30:00+05:30", "1.5")   # Monday evening     1.5 x 6  =  9.00

    body = estimate(client, lab_id, granularity="week").json()
    total = body["total"]
    assert total["kwh"] == "5.0000"
    assert total["estimated_cost"] == "42.00"
    assert total["estimated_emissions"] == "2.5000"
    assert total["kwh_without_tariff"] == "0.0000"
    assert total["kwh_by_reading_type"]["simulated"] == "0.5000"
    assert body["currency"] == "INR" and body["emission_unit"] == "kgCO2e/kWh"


def test_hours_outside_every_band_are_reported_not_priced(client, make_lab):
    lab_id = make_lab()
    client.post("/api/tariffs", json=PEAK)
    client.post("/api/emission-factors", json=FACTOR)
    reading(client, lab_id, "2026-10-05T10:30:00+05:30", "2.0")
    reading(client, lab_id, "2026-10-05T03:30:00+05:30", "1.0")  # no band covers 03:00
    total = estimate(client, lab_id).json()["total"]
    assert total["estimated_cost"] == "24.00"
    assert total["kwh_with_tariff"] == "2.0000"
    assert total["kwh_without_tariff"] == "1.0000"


def test_emission_factor_changes_at_its_effective_date(client, make_lab):
    lab_id = make_lab()
    client.post("/api/tariffs", json=PEAK)
    client.post("/api/emission-factors", json={**FACTOR, "value": "0.8000", "effective_to": "2026-06-30",
                                               "version_or_year": "test-first-half"})
    client.post("/api/emission-factors", json={**FACTOR, "value": "0.6000", "effective_from": "2026-07-01",
                                               "version_or_year": "test-second-half"})
    reading(client, lab_id, "2026-06-15T10:00:00+05:30", "1.0")
    reading(client, lab_id, "2026-07-15T10:00:00+05:30", "1.0")
    body = client.get("/api/estimates/cost-emissions", params={
        "start": "2026-06-01T00:00:00Z", "end": "2026-08-01T00:00:00Z", "lab_id": lab_id}).json()
    emissions = {b["period"]: b["estimated_emissions"] for b in body["buckets"]}
    assert emissions == {"2026-06-15": "0.8000", "2026-07-15": "0.6000"}
    assert body["total"]["estimated_emissions"] == "1.4000"


def test_savings_are_never_calculated_and_the_estimate_is_labelled(client, make_lab):
    lab_id = make_lab()
    client.post("/api/tariffs", json=PEAK)
    client.post("/api/emission-factors", json=FACTOR)
    reading(client, lab_id, "2026-10-05T10:30:00+05:30", "2.0")
    body = estimate(client).json()
    assert "estimate" in body["labels"]["cost"].lower()
    assert "not calculated" in body["labels"]["savings"].lower()
    assert "savings" not in body["total"]


def test_mixed_currencies_leave_the_currency_unset(client, make_lab):
    make_lab()
    client.post("/api/tariffs", json=PEAK)
    client.post("/api/tariffs", json={**WEEKEND, "currency": "USD"})
    client.post("/api/emission-factors", json=FACTOR)
    assert estimate(client).json()["currency"] is None


def test_unknown_lab_and_oversized_window_are_refused(client, make_lab):
    client.post("/api/tariffs", json=PEAK)
    client.post("/api/emission-factors", json=FACTOR)
    assert estimate(client, lab_id=9999).status_code == 404
    response = client.get("/api/estimates/cost-emissions", params={
        "start": "2024-01-01T00:00:00Z", "end": "2026-10-01T00:00:00Z"})
    assert response.status_code == 422


def test_staff_cannot_change_tariffs_but_managers_can(role_client):
    staff, evaluator, manager = role_client("staff"), role_client("evaluator"), role_client("lab_manager")
    assert staff.post("/api/tariffs", json=PEAK).status_code == 403
    assert evaluator.post("/api/emission-factors", json=FACTOR).status_code == 403
    assert manager.post("/api/tariffs", json=PEAK).status_code == 201
    assert evaluator.get("/api/tariffs").status_code == 200
