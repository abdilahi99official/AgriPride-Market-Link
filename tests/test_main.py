import os
from datetime import timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_marketlink.db")
os.environ.setdefault("FRESHNESS_THRESHOLD_HOURS", "24")

import pytest
from fastapi.testclient import TestClient

from app.main import connect, iso_now, reset_database, seed_demo_data, seed_demo_on_start_if_enabled, utcnow, app


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_database() -> None:
    reset_database()
    client.cookies.clear()


def login(username: str = "submitter", password: str = "submitter-pass") -> TestClient:
    response = client.post(
        "/officer/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client


def submit_price(crop: str = "maize", min_price: int = 600, max_price: int = 750) -> int:
    login()
    response = client.post(
        "/officer/prices/new",
        data={"crop": crop, "min_price": min_price, "max_price": max_price, "source": "Test source"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    with connect() as conn:
        return conn.execute("SELECT id FROM price_records ORDER BY id DESC LIMIT 1").fetchone()["id"]


def approve_price(price_id: int) -> None:
    login("reviewer", "reviewer-pass")
    response = client.post(
        f"/officer/prices/{price_id}/review",
        data={"action": "approve", "note": "ok"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def seed_approved(crop: str = "maize", min_price: int = 600, max_price: int = 750, *, stale: bool = False) -> None:
    reviewed_at = (utcnow() - timedelta(hours=48)).isoformat() if stale else iso_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO price_records
            (crop, min_price, max_price, source, status, submitted_by, reviewed_by, created_at, updated_at, reviewed_at)
            VALUES (?, ?, ?, 'Test source', 'approved', 'OFFICER-A', 'OFFICER-B', ?, ?, ?)
            """,
            (crop, min_price, max_price, reviewed_at, reviewed_at, reviewed_at),
        )


def count_rows(table: str) -> int:
    with connect() as conn:
        return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_farmer_page() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "AgriPride Kibaigwa MarketLink" in response.text
    assert "Human-approved source" in response.text


def test_lite_page() -> None:
    response = client.get("/lite")
    assert response.status_code == 200
    assert "MarketLink Lite" in response.text
    assert "<script" not in response.text.lower()


def test_market_page() -> None:
    seed_demo_data()
    response = client.get("/market")
    assert response.status_code == 200
    assert "Public Market Dashboard" in response.text
    assert "Historical approved prices" in response.text


def test_plain_text_price_endpoint() -> None:
    seed_approved()
    response = client.get("/api/v1/prices/maize.txt")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "Mahindi" in response.text


def test_invalid_range_rejected() -> None:
    login()
    response = client.post(
        "/officer/prices/new",
        data={"crop": "maize", "min_price": 800, "max_price": 700, "source": "Bad"},
    )
    assert response.status_code == 400


def test_submission_pending() -> None:
    price_id = submit_price()
    with connect() as conn:
        row = conn.execute("SELECT status FROM price_records WHERE id=?", (price_id,)).fetchone()
    assert row["status"] == "pending"


def test_self_approval_blocked() -> None:
    price_id = submit_price()
    response = client.post(
        f"/officer/prices/{price_id}/review",
        data={"action": "approve"},
    )
    assert response.status_code == 403
    with connect() as conn:
        audit = conn.execute("SELECT action FROM audit_events WHERE action='self_approval_blocked'").fetchone()
    assert audit is not None


def test_reviewer_approval() -> None:
    price_id = submit_price()
    approve_price(price_id)
    with connect() as conn:
        row = conn.execute("SELECT status, reviewed_by FROM price_records WHERE id=?", (price_id,)).fetchone()
    assert row["status"] == "approved"
    assert row["reviewed_by"] == "OFFICER-B"


def test_fresh_stale_unavailable_states() -> None:
    seed_approved("maize", stale=False)
    seed_approved("sunflower", stale=True)
    assert client.get("/api/v1/prices/maize").json()["state"] == "fresh"
    assert client.get("/api/v1/prices/sunflower").json()["state"] == "stale"
    assert client.get("/api/v1/prices/groundnuts").json()["state"] == "unavailable"


def test_audit_events() -> None:
    price_id = submit_price()
    approve_price(price_id)
    assert count_rows("audit_events") >= 3


def test_multi_crop_support() -> None:
    seed_demo_data()
    for crop in ("maize", "sunflower", "groundnuts"):
        response = client.get(f"/api/v1/prices/{crop}")
        assert response.status_code == 200
        assert response.json()["crop"] == crop


def test_startup_demo_seed_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEED_DEMO_ON_START", raising=False)
    assert seed_demo_on_start_if_enabled() is False
    assert count_rows("price_records") == 0


def test_startup_demo_seed_enabled_is_idempotent_and_no_farmer_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEED_DEMO_ON_START", "true")
    assert seed_demo_on_start_if_enabled() is True
    assert seed_demo_on_start_if_enabled() is False
    with connect() as conn:
        crops = conn.execute("SELECT crop FROM price_records WHERE status='approved' ORDER BY crop").fetchall()
    assert [row["crop"] for row in crops] == ["groundnuts", "maize", "sunflower"]
    assert count_rows("price_records") == 3
    assert count_rows("farmer_queries") == 0


def test_startup_demo_seed_skips_when_approved_records_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    seed_approved("maize")
    monkeypatch.setenv("SEED_DEMO_ON_START", "true")
    assert seed_demo_on_start_if_enabled() is False
    assert count_rows("price_records") == 1


def test_ussd_menu_initial_response_starts_with_con() -> None:
    response = client.post(
        "/channels/ussd/callback",
        data={"sessionId": "s1", "serviceCode": "*700#", "phoneNumber": "+255700123456", "text": ""},
    )
    assert response.status_code == 200
    assert response.text.startswith("CON ")


def test_ussd_crop_selection_returns_end() -> None:
    seed_approved()
    response = client.post(
        "/channels/ussd/callback",
        data={"sessionId": "s1", "serviceCode": "*700#", "phoneNumber": "+255700123456", "text": "1"},
    )
    assert response.text.startswith("END ")
    assert "Mahindi" in response.text


def test_ussd_unavailable_state() -> None:
    response = client.post(
        "/channels/ussd/callback",
        data={"sessionId": "s1", "serviceCode": "*700#", "phoneNumber": "+255700123456", "text": "3"},
    )
    assert response.text.startswith("END ")
    assert "Hakuna bei" in response.text


def test_sms_crop_keyword_parsing() -> None:
    seed_approved()
    response = client.post("/channels/sms/inbound", data={"from": "+255700123456", "text": "MAHINDI"})
    assert response.status_code == 200
    assert "Mahindi" in response.json()["message"]
    assert "rejea" in response.json()["message"]


def test_sms_unknown_keyword_help() -> None:
    response = client.post("/channels/sms/inbound", data={"from": "+255700123456", "text": "BEI"})
    assert response.status_code == 200
    assert "Tuma MAHINDI" in response.json()["message"]


def test_masked_phone_stored_in_channel_log() -> None:
    client.post("/channels/sms/inbound", data={"from": "+255700123456", "text": "MAHINDI"})
    with connect() as conn:
        row = conn.execute("SELECT masked_phone FROM farmer_queries WHERE channel='sms'").fetchone()
    assert row["masked_phone"] == "255***56"
    assert "700123456" not in row["masked_phone"]


def test_guardian_below_range_flag() -> None:
    seed_approved("maize", 600, 750)
    client.post(
        "/agent-demo",
        data={
            "crop": "maize",
            "offered_price": 500,
            "quantity_kg": 100,
            "scale_id_state": "present",
            "payment_state": "paid",
            "actor_record_state": "present",
        },
        follow_redirects=False,
    )
    with connect() as conn:
        row = conn.execute("SELECT flag FROM guardian_flags").fetchone()
    assert row["flag"] == "offer_below_reference_range"


def test_guardian_missing_scale_flag() -> None:
    seed_approved("maize", 600, 750)
    client.post(
        "/agent-demo",
        data={
            "crop": "maize",
            "offered_price": 650,
            "quantity_kg": 100,
            "scale_id_state": "missing",
            "payment_state": "paid",
            "actor_record_state": "present",
        },
        follow_redirects=False,
    )
    with connect() as conn:
        row = conn.execute("SELECT flag FROM guardian_flags").fetchone()
    assert row["flag"] == "missing_scale_id"


def test_hunter_briefing() -> None:
    seed_approved("maize", 600, 750)
    client.post(
        "/agent-demo",
        data={
            "crop": "maize",
            "offered_price": 500,
            "quantity_kg": 100,
            "scale_id_state": "missing",
            "payment_state": "paid",
            "actor_record_state": "present",
        },
        follow_redirects=False,
    )
    with connect() as conn:
        row = conn.execute("SELECT briefing FROM hunter_briefings").fetchone()
    assert "human review" in row["briefing"]
    assert "No automatic punishment" in row["briefing"]


def test_clean_case_no_hunter_briefing() -> None:
    seed_approved("maize", 600, 750)
    client.post(
        "/agent-demo",
        data={
            "crop": "maize",
            "offered_price": 650,
            "quantity_kg": 100,
            "scale_id_state": "present",
            "payment_state": "paid",
            "actor_record_state": "present",
        },
        follow_redirects=False,
    )
    assert count_rows("hunter_briefings") == 0


def test_human_decision_logged() -> None:
    seed_approved("maize", 600, 750)
    client.post(
        "/agent-demo",
        data={
            "crop": "maize",
            "offered_price": 500,
            "quantity_kg": 100,
            "scale_id_state": "missing",
            "payment_state": "paid",
            "actor_record_state": "present",
        },
        follow_redirects=False,
    )
    with connect() as conn:
        case_id = conn.execute("SELECT id FROM agent_demo_cases").fetchone()["id"]
    response = client.post(
        f"/agent-demo/{case_id}/review",
        data={"reviewer_id": "human", "decision": "resolved", "note": "called officer"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert count_rows("human_review_decisions") == 1


def test_no_automatic_punishment() -> None:
    seed_approved("maize", 600, 750)
    client.post(
        "/agent-demo",
        data={
            "crop": "maize",
            "offered_price": 500,
            "quantity_kg": 100,
            "scale_id_state": "missing",
            "payment_state": "disputed",
            "actor_record_state": "missing",
        },
        follow_redirects=False,
    )
    with connect() as conn:
        case = conn.execute("SELECT status FROM agent_demo_cases").fetchone()
    assert case["status"] == "human_review_required"
    assert "blacklist" not in case["status"]


def test_officer_auth() -> None:
    assert client.get("/officer/dashboard").status_code == 401
    login("reviewer", "reviewer-pass")
    assert client.get("/officer/dashboard").status_code == 200


def test_service_worker_and_manifest_available() -> None:
    manifest = client.get("/manifest.webmanifest")
    worker = client.get("/service-worker.js")
    assert manifest.status_code == 200
    assert manifest.json()["short_name"] == "MarketLink"
    assert worker.status_code == 200
    assert "/officer" in worker.text
    assert "/api" in worker.text


def test_channel_demo_and_delivery_report() -> None:
    assert client.get("/channels/demo").status_code == 200
    response = client.post(
        "/channels/sms/delivery-report",
        data={"provider": "mock", "messageId": "m1", "status": "Delivered", "phoneNumber": "+255700123456"},
    )
    assert response.json() == {"status": "received"}
    assert count_rows("channel_delivery_events") == 1
