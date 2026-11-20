def reading(lab_id, timestamp, value, reading_type):
    return {"lab_id": lab_id, "timestamp": timestamp, "value": value,
            "reading_type": reading_type, "source": "test"}


def seed(client, make_lab):
    lab_id = make_lab(timezone="Asia/Kolkata")
    # 20:00 UTC on 1 Oct is 01:30 on 2 Oct in India, so it belongs to the 2 Oct bucket.
    client.post("/api/readings", json=reading(lab_id, "2026-10-01T20:00:00Z", "1.0", "measured"))
    # 10:00 UTC on 1 Oct is 15:30 on 1 Oct in India.
    client.post("/api/readings", json=reading(lab_id, "2026-10-01T10:00:00Z", "2.0", "simulated"))
    return lab_id


def test_daily_buckets_use_the_lab_local_day(client, make_lab):
    seed(client, make_lab)
    body = client.get("/api/analytics/consumption",
                      params={"start": "2026-09-30T00:00:00Z", "end": "2026-10-04T00:00:00Z"}).json()
    by_period = {b["period"]: b for b in body["buckets"]}
    assert set(by_period) == {"2026-10-01", "2026-10-02"}
    assert float(by_period["2026-10-01"]["simulated_kwh"]) == 2.0
    assert float(by_period["2026-10-02"]["measured_kwh"]) == 1.0


def test_measured_and_simulated_are_kept_separate(client, make_lab):
    seed(client, make_lab)
    bucket = client.get("/api/analytics/consumption",
                        params={"start": "2026-09-30T00:00:00Z", "end": "2026-10-04T00:00:00Z"}).json()["buckets"]
    day_one = next(b for b in bucket if b["period"] == "2026-10-01")
    assert float(day_one["measured_kwh"]) == 0.0
    assert float(day_one["simulated_kwh"]) == 2.0


def test_weekly_buckets_start_on_monday(client, make_lab):
    seed(client, make_lab)
    body = client.get("/api/analytics/consumption", params={
        "start": "2026-09-30T00:00:00Z", "end": "2026-10-04T00:00:00Z", "granularity": "week"}).json()
    assert [b["period"] for b in body["buckets"]] == ["2026-09-28"]
    assert float(body["buckets"][0]["total_kwh"]) == 3.0


def test_monthly_buckets(client, make_lab):
    seed(client, make_lab)
    body = client.get("/api/analytics/consumption", params={
        "start": "2026-09-30T00:00:00Z", "end": "2026-11-01T00:00:00Z", "granularity": "month"}).json()
    assert [b["period"] for b in body["buckets"]] == ["2026-10"]


def test_filter_by_reading_type(client, make_lab):
    seed(client, make_lab)
    body = client.get("/api/analytics/consumption", params={
        "start": "2026-09-30T00:00:00Z", "end": "2026-10-04T00:00:00Z", "reading_type": "measured"}).json()
    assert [b["period"] for b in body["buckets"]] == ["2026-10-02"]


def test_window_must_be_valid(client):
    base = {"start": "2026-10-01T00:00:00Z"}
    assert client.get("/api/analytics/consumption", params={**base, "end": "2026-09-30T00:00:00Z"}).status_code == 422
    assert client.get("/api/analytics/consumption",
                      params={**base, "end": "2026-10-02T00:00:00Z"}).status_code == 200
    assert client.get("/api/analytics/consumption",
                      params={"start": "2024-01-01T00:00:00Z", "end": "2026-10-01T00:00:00Z"}).status_code == 422
    assert client.get("/api/analytics/consumption",
                      params={"start": "2026-10-01T00:00:00", "end": "2026-10-02T00:00:00Z"}).status_code == 422
