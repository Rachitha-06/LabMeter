from app.auth.passwords import hash_password
from app.db import models as m
from app.db.session import make_session_factory


def lab_payload(**overrides):
    payload = {
        "name": "Lab A", "building": "Block A", "lab_type": "Teaching",
        "computer_count": 30, "timezone": "Asia/Kolkata",
    }
    payload.update(overrides)
    return payload


def add_user(engine, email, password, role, is_active=True):
    with make_session_factory(engine)() as session:
        session.add(m.User(email=email, password_hash=hash_password(password), role=role, is_active=is_active))
        session.commit()


def sign_in(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def load_synthetic_dataset(client, dataset_dir):
    """Load the synthetic data through the API, the same way an operator would. Returns name -> id.

    Laboratories, equipment, operating hours, the academic calendar, and readings are all loaded.
    """
    import csv
    with (dataset_dir / "labs.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            client.post("/api/labs", json=lab_payload(
                name=row["name"], building=row["building"], lab_type=row["lab_type"],
                computer_count=int(row["computer_count"]), timezone=row["timezone"]))
    ids = {lab["name"]: lab["id"] for lab in client.get("/api/labs").json()}
    with (dataset_dir / "schedules.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            response = client.post(f"/api/labs/{ids[row['lab_name']]}/schedules", json={
                "weekday": int(row["weekday"]), "open_time": f"{row['open_time']}:00",
                "close_time": f"{row['close_time']}:00", "valid_from": row["valid_from"]})
            assert response.status_code == 201, response.text
    with (dataset_dir / "equipment.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            client.post(f"/api/labs/{ids[row['lab_name']]}/equipment", json={
                "equipment_type": row["equipment_type"], "quantity": int(row["quantity"]),
                "rated_power_w": row["rated_power_w"]})
    with (dataset_dir / "calendar.csv").open(encoding="utf-8") as handle:
        days = [{"day": row["day"], "is_holiday": row["is_holiday"] == "True",
                 "is_exam_period": row["is_exam_period"] == "True", "label": row["label"] or None}
                for row in csv.DictReader(handle)]
    response = client.put("/api/calendar", json={"days": days})
    assert response.status_code == 200, response.text
    response = client.post("/api/imports/readings",
                           files={"file": ("readings.csv", (dataset_dir / "readings.csv").read_bytes(), "text/csv")})
    assert response.status_code == 200, response.text
    return ids
