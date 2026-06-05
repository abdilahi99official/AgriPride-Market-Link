from __future__ import annotations

import csv
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from dotenv import load_dotenv


load_dotenv()

APP_NAME = "AgriPride Kibaigwa MarketLink"
DEFAULT_DB = "sqlite:///./marketlink.db"

CROPS: dict[str, dict[str, str]] = {
    "maize": {"sw": "Mahindi", "en": "Maize", "sms": "MAHINDI"},
    "sunflower": {"sw": "Alizeti", "en": "Sunflower", "sms": "ALIZETI"},
    "groundnuts": {"sw": "Karanga", "en": "Groundnuts", "sms": "KARANGA"},
}

SMS_KEYWORDS = {
    "MAHINDI": "maize",
    "MAIZE": "maize",
    "ALIZETI": "sunflower",
    "SUNFLOWER": "sunflower",
    "KARANGA": "groundnuts",
    "GROUNDNUTS": "groundnuts",
}

USSD_SELECTIONS = {"1": "maize", "2": "sunflower", "3": "groundnuts"}

app = FastAPI(
    title=APP_NAME,
    description="Low-bandwidth, human-supervised market transparency for Kibaigwa.",
    version="1.0.0",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utcnow().isoformat()


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DB)


def is_postgres_url() -> bool:
    return database_url().startswith(("postgres://", "postgresql://"))


def database_path() -> Path:
    url = os.getenv("DATABASE_URL", DEFAULT_DB)
    if url.startswith("sqlite:///"):
        return Path(url.removeprefix("sqlite:///"))
    return Path("marketlink.db")


class PgCursor:
    def __init__(self, cursor: Any, *, capture_last_id: bool = False) -> None:
        self.cursor = cursor
        self._lastrowid = None
        if capture_last_id:
            row = cursor.fetchone()
            self._lastrowid = row["id"] if row else None

    @property
    def lastrowid(self) -> int | None:
        return self._lastrowid

    def fetchone(self) -> Any:
        return self.cursor.fetchone()

    def fetchall(self) -> list[Any]:
        return self.cursor.fetchall()


class PgConnection:
    def __init__(self, url: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("PostgreSQL DATABASE_URL requires psycopg[binary] from requirements.txt") from exc
        self.conn = psycopg.connect(url, row_factory=dict_row)

    def __enter__(self) -> "PgConnection":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> PgCursor:
        capture_last_id = False
        normalized = sql.lstrip().lower()
        if normalized.startswith("insert into price_records") or normalized.startswith("insert into agent_demo_cases"):
            if "returning id" not in normalized:
                sql = f"{sql.rstrip()} RETURNING id"
                capture_last_id = True
        sql = sql.replace("?", "%s").replace("datetime(reviewed_at)", "reviewed_at")
        return PgCursor(self.conn.execute(sql, params), capture_last_id=capture_last_id)

    def executescript(self, sql: str) -> None:
        pg_sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        self.conn.execute(pg_sql)


def connect() -> sqlite3.Connection | PgConnection:
    if is_postgres_url():
        return PgConnection(database_url())
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS price_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                crop TEXT NOT NULL,
                min_price INTEGER NOT NULL,
                max_price INTEGER NOT NULL,
                unit TEXT NOT NULL DEFAULT 'TZS/kg',
                source TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                submitted_by TEXT NOT NULL,
                reviewed_by TEXT,
                review_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                reviewed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS farmer_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                crop TEXT,
                response_state TEXT NOT NULL,
                masked_phone TEXT,
                session_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS channel_delivery_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                message_id TEXT,
                status TEXT NOT NULL,
                masked_phone TEXT,
                raw_state TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agent_demo_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                crop TEXT NOT NULL,
                offered_price INTEGER NOT NULL,
                quantity_kg INTEGER NOT NULL,
                scale_id_state TEXT NOT NULL,
                payment_state TEXT NOT NULL,
                actor_record_state TEXT NOT NULL,
                reference_min INTEGER,
                reference_max INTEGER,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS guardian_flags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                flag TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hunter_briefings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                briefing TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS human_review_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                reviewer_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            );
            """
        )


def reset_database() -> None:
    init_db()
    with connect() as conn:
        for table in (
            "price_records",
            "audit_events",
            "farmer_queries",
            "channel_delivery_events",
            "agent_demo_cases",
            "guardian_flags",
            "hunter_briefings",
            "human_review_decisions",
        ):
            conn.execute(f"DELETE FROM {table}")


@app.on_event("startup")
def startup() -> None:
    init_db()


def render_page(title: str, body: str, *, lite: bool = False) -> HTMLResponse:
    css = (
        "<style>body{font-family:Arial,sans-serif;margin:0;color:#172018;background:#f7f8f3}"
        "header,main{max-width:920px;margin:auto;padding:16px}.band{background:#244b35;color:white}"
        "a{color:#174e7a}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}"
        ".card,form,table{background:white;border:1px solid #d7ddcf;border-radius:6px;padding:12px}"
        "input,select,button,textarea{font:inherit;padding:9px;margin:4px 0;max-width:100%}"
        "button{background:#1f6b45;color:white;border:0;border-radius:4px;cursor:pointer}"
        ".warn{color:#8a4b00}.ok{color:#17623d}.bad{color:#8b1d1d}"
        "table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #e4e7df;padding:8px;text-align:left}"
        "</style>"
    )
    if lite:
        css = "<style>body{font-family:serif;max-width:760px;margin:12px}input,select,button{font:inherit}</style>"
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title><link rel='manifest' href='/manifest.webmanifest'>{css}</head>"
        f"<body><header class='band'><h1>{title}</h1></header><main>{body}</main></body></html>"
    )
    return HTMLResponse(html)


def crop_options(selected: str = "maize") -> str:
    return "".join(
        f"<option value='{key}' {'selected' if key == selected else ''}>{meta['sw']} / {meta['en']}</option>"
        for key, meta in CROPS.items()
    )


def freshness_hours() -> int:
    return int(os.getenv("FRESHNESS_THRESHOLD_HOURS", "24"))


def log_audit(actor_id: str, action: str, entity_type: str, entity_id: Any = None, details: str = "") -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO audit_events (actor_id, action, entity_type, entity_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (actor_id, action, entity_type, str(entity_id) if entity_id is not None else None, details, iso_now()),
        )


def log_query(
    channel: str,
    crop: str | None,
    response_state: str,
    *,
    phone: str | None = None,
    session_id: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO farmer_queries (channel, crop, response_state, masked_phone, session_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (channel, crop, response_state, mask_phone(phone), session_id, iso_now()),
        )


def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) <= 4:
        return "****"
    return f"{digits[:3]}***{digits[-2:]}"


def latest_approved(crop: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            """
            SELECT * FROM price_records
            WHERE crop = ? AND status = 'approved'
            ORDER BY datetime(reviewed_at) DESC, id DESC
            LIMIT 1
            """,
            (crop,),
        ).fetchone()


def price_state(crop: str) -> dict[str, Any]:
    if crop not in CROPS:
        raise HTTPException(status_code=404, detail="Unsupported crop")
    row = latest_approved(crop)
    if row is None:
        return {"crop": crop, "state": "unavailable", "record": None}
    reviewed_at = parse_dt(row["reviewed_at"])
    is_fresh = reviewed_at is not None and reviewed_at >= utcnow() - timedelta(hours=freshness_hours())
    return {"crop": crop, "state": "fresh" if is_fresh else "stale", "record": dict(row)}


def price_message(crop: str, *, lang: str = "sw", channel: str = "web") -> tuple[str, str]:
    state = price_state(crop)
    label = CROPS[crop]["sw"] if lang == "sw" else CROPS[crop]["en"]
    record = state["record"]
    if state["state"] == "unavailable":
        if lang == "sw":
            return "unavailable", f"Hakuna bei iliyoidhinishwa kwa {label} kwa sasa."
        return "unavailable", f"No approved reference price is available for {label} right now."
    timestamp = record["reviewed_at"][:16].replace("T", " ")
    range_text = f"{record['min_price']}-{record['max_price']} {record['unit']}"
    stale_note = "TAHADHARI: bei imepitwa na muda. " if state["state"] == "stale" and lang == "sw" else ""
    if lang == "sw":
        message = (
            f"{stale_note}{label}: {range_text}. Imethibitishwa {timestamp}. "
            "Ni bei ya rejea, si ahadi ya mnunuzi."
        )
    else:
        message = (
            f"{label}: {range_text}. Approved {timestamp}. "
            "Reference range only, not a guaranteed buyer offer."
        )
    if channel == "sms" and len(message) > 155:
        message = message[:152] + "..."
    return state["state"], message


def current_officer(request: Request) -> dict[str, str] | None:
    raw = request.cookies.get("officer")
    if not raw:
        return None
    parts = raw.split("|")
    if len(parts) != 3:
        return None
    return {"officer_id": parts[0], "role": parts[1], "username": parts[2]}


def require_officer(request: Request) -> dict[str, str]:
    officer = current_officer(request)
    if officer is None:
        raise HTTPException(status_code=401, detail="Officer login required")
    return officer


def env_user(prefix: str, defaults: dict[str, str]) -> dict[str, str]:
    return {
        "username": os.getenv(f"{prefix}_USERNAME", defaults["username"]),
        "password": os.getenv(f"{prefix}_PASSWORD", defaults["password"]),
        "officer_id": os.getenv(f"{prefix}_OFFICER_ID", defaults["officer_id"]),
        "role": defaults["role"],
    }


def officer_accounts() -> list[dict[str, str]]:
    return [
        env_user("SUBMITTER", {"username": "submitter", "password": "submitter-pass", "officer_id": "OFFICER-A", "role": "submitter"}),
        env_user("REVIEWER", {"username": "reviewer", "password": "reviewer-pass", "officer_id": "OFFICER-B", "role": "reviewer"}),
    ]


@app.get("/health")
def health_check() -> dict[str, str]:
    init_db()
    return {"status": "healthy"}


@app.get("/", response_class=HTMLResponse)
def farmer_home(crop: str = "maize", lang: str = "sw") -> HTMLResponse:
    init_db()
    if crop not in CROPS:
        crop = "maize"
    state, message = price_message(crop, lang=lang, channel="web")
    log_query("web", crop, state)
    language_link = "en" if lang == "sw" else "sw"
    body = f"""
    <section class='card'>
      <p><a href='/?crop={crop}&lang={language_link}'>Kiswahili / English</a> |
      <a href='/lite?crop={crop}'>Lite</a> | <a href='/market'>Market</a></p>
      <form method='get' action='/'>
        <label>Crop</label><br>
        <select name='crop'>{crop_options(crop)}</select>
        <input type='hidden' name='lang' value='{lang}'>
        <button type='submit'>Check price</button>
      </form>
      <h2>{CROPS[crop]['sw']} / {CROPS[crop]['en']}</h2>
      <p class='{'ok' if state == 'fresh' else 'warn'}'>{message}</p>
      <p>Human-approved source only. No account required.</p>
    </section>
    """
    return render_page(APP_NAME, body)


@app.get("/lite", response_class=HTMLResponse)
def lite(crop: str = "maize", lang: str = "sw") -> HTMLResponse:
    init_db()
    if crop not in CROPS:
        crop = "maize"
    state, message = price_message(crop, lang=lang, channel="lite")
    log_query("lite", crop, state)
    body = f"""
    <p><a href='/'>Web</a> <a href='/market'>Market</a></p>
    <form method='get' action='/lite'>
      <label>Bei ya zao</label><br>
      <select name='crop'>{crop_options(crop)}</select>
      <select name='lang'><option value='sw'>Kiswahili</option><option value='en'>English</option></select>
      <button>Angalia</button>
    </form>
    <h2>{CROPS[crop]['sw']} / {CROPS[crop]['en']}</h2>
    <p>{message}</p>
    <p>Bei ni rejea tu. Si ahadi ya mnunuzi.</p>
    """
    return render_page("MarketLink Lite", body, lite=True)


@app.get("/market", response_class=HTMLResponse)
def market() -> HTMLResponse:
    init_db()
    cards = []
    history_rows = []
    with connect() as conn:
        history = conn.execute(
            "SELECT * FROM price_records WHERE status='approved' ORDER BY datetime(reviewed_at) DESC LIMIT 20"
        ).fetchall()
    for crop in CROPS:
        state, message = price_message(crop, lang="sw")
        cards.append(f"<article class='card'><h2>{CROPS[crop]['sw']} / {CROPS[crop]['en']}</h2><p>{message}</p><p>Status: {state}</p></article>")
    for row in history:
        history_rows.append(
            f"<tr><td>{row['reviewed_at'][:10]}</td><td>{CROPS[row['crop']]['en']}</td>"
            f"<td>{row['min_price']}-{row['max_price']} {row['unit']}</td><td>{row['source']}</td></tr>"
        )
    body = (
        "<p><a href='/'>Farmer page</a> <a href='/lite'>Lite</a> <a href='/channels/demo'>SMS/USSD demo</a></p>"
        f"<section class='grid'>{''.join(cards)}</section>"
        "<h2>Historical approved prices</h2><table><tr><th>Date</th><th>Crop</th><th>Range</th><th>Source</th></tr>"
        f"{''.join(history_rows) or '<tr><td colspan=4>No approved history yet.</td></tr>'}</table>"
    )
    return render_page("Public Market Dashboard", body)


@app.get("/api/v1/prices/{crop}.txt", response_class=PlainTextResponse)
def api_price_text(crop: str) -> PlainTextResponse:
    init_db()
    state, message = price_message(crop, lang="sw", channel="txt")
    log_query("txt", crop, state)
    return PlainTextResponse(message)


@app.get("/api/v1/prices/{crop}")
def api_price(crop: str) -> dict[str, Any]:
    init_db()
    state = price_state(crop)
    log_query("api", crop, state["state"])
    record = state["record"]
    if record is None:
        return {"crop": crop, "state": "unavailable", "message": "No approved reference price available"}
    return {
        "crop": crop,
        "label": CROPS[crop],
        "state": state["state"],
        "min_price": record["min_price"],
        "max_price": record["max_price"],
        "unit": record["unit"],
        "source": record["source"],
        "approved_at": record["reviewed_at"],
        "disclaimer": "Reference range only, not a guaranteed buyer offer.",
    }


@app.get("/officer/login", response_class=HTMLResponse)
def login_form() -> HTMLResponse:
    body = """
    <form method='post' action='/officer/login'>
      <label>Username</label><br><input name='username'><br>
      <label>Password</label><br><input name='password' type='password'><br>
      <button>Login</button>
    </form>
    """
    return render_page("Officer Login", body)


@app.post("/officer/login")
def login(username: str = Form(...), password: str = Form(...)) -> RedirectResponse:
    for account in officer_accounts():
        if username == account["username"] and password == account["password"]:
            response = RedirectResponse("/officer/dashboard", status_code=303)
            response.set_cookie("officer", f"{account['officer_id']}|{account['role']}|{account['username']}", httponly=True)
            log_audit(account["officer_id"], "login", "Officer")
            return response
    raise HTTPException(status_code=401, detail="Invalid officer credentials")


@app.post("/officer/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/officer/login", status_code=303)
    response.delete_cookie("officer")
    return response


@app.get("/officer/dashboard", response_class=HTMLResponse)
def officer_dashboard(request: Request) -> HTMLResponse:
    officer = require_officer(request)
    with connect() as conn:
        pending = conn.execute("SELECT COUNT(*) AS n FROM price_records WHERE status='pending'").fetchone()["n"]
        approved = conn.execute("SELECT COUNT(*) AS n FROM price_records WHERE status='approved'").fetchone()["n"]
    body = f"""
    <p>Signed in as {officer['username']} ({officer['officer_id']}).</p>
    <p><a href='/officer/prices'>Prices</a> <a href='/officer/prices/new'>Submit range</a>
    <a href='/officer/audit'>Audit</a> <a href='/officer/metrics'>Metrics</a></p>
    <section class='grid'><article class='card'><h2>{pending}</h2><p>Pending</p></article>
    <article class='card'><h2>{approved}</h2><p>Approved</p></article></section>
    <form method='post' action='/officer/logout'><button>Logout</button></form>
    """
    return render_page("Officer Dashboard", body)


@app.get("/officer/prices", response_class=HTMLResponse)
def officer_prices(request: Request) -> HTMLResponse:
    require_officer(request)
    with connect() as conn:
        rows = conn.execute("SELECT * FROM price_records ORDER BY id DESC").fetchall()
    table = "".join(
        f"<tr><td>{row['id']}</td><td>{row['crop']}</td><td>{row['min_price']}-{row['max_price']}</td>"
        f"<td>{row['status']}</td><td><a href='/officer/prices/{row['id']}/review'>Review</a></td></tr>"
        for row in rows
    )
    body = (
        "<p><a href='/officer/dashboard'>Dashboard</a> <a href='/officer/prices/new'>New range</a></p>"
        "<table><tr><th>ID</th><th>Crop</th><th>Range</th><th>Status</th><th></th></tr>"
        f"{table or '<tr><td colspan=5>No records yet.</td></tr>'}</table>"
    )
    return render_page("Officer Prices", body)


@app.get("/officer/prices/new", response_class=HTMLResponse)
def new_price_form(request: Request) -> HTMLResponse:
    require_officer(request)
    body = f"""
    <form method='post' action='/officer/prices/new'>
      <label>Crop</label><br><select name='crop'>{crop_options()}</select><br>
      <label>Minimum TZS/kg</label><br><input name='min_price' type='number' min='1'><br>
      <label>Maximum TZS/kg</label><br><input name='max_price' type='number' min='1'><br>
      <label>Source</label><br><input name='source' value='Kibaigwa market officer'><br>
      <button>Submit for review</button>
    </form>
    """
    return render_page("Submit Price Range", body)


@app.post("/officer/prices/new")
def create_price(
    request: Request,
    crop: str = Form(...),
    min_price: int = Form(...),
    max_price: int = Form(...),
    source: str = Form("Kibaigwa market officer"),
) -> RedirectResponse:
    officer = require_officer(request)
    if crop not in CROPS or min_price <= 0 or max_price <= 0 or min_price > max_price:
        raise HTTPException(status_code=400, detail="Invalid crop or price range")
    now = iso_now()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO price_records (crop, min_price, max_price, source, status, submitted_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (crop, min_price, max_price, source, officer["officer_id"], now, now),
        )
        price_id = cursor.lastrowid
    log_audit(officer["officer_id"], "submit_price_range", "PriceRecord", price_id, crop)
    return RedirectResponse("/officer/prices", status_code=303)


@app.get("/officer/prices/{price_id}/review", response_class=HTMLResponse)
def review_form(price_id: int, request: Request) -> HTMLResponse:
    require_officer(request)
    with connect() as conn:
        row = conn.execute("SELECT * FROM price_records WHERE id=?", (price_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Price record not found")
    body = f"""
    <p>{row['crop']} {row['min_price']}-{row['max_price']} {row['unit']} submitted by {row['submitted_by']}.</p>
    <form method='post' action='/officer/prices/{price_id}/review'>
      <label>Review note</label><br><textarea name='note'></textarea><br>
      <button name='action' value='approve'>Approve</button>
      <button name='action' value='reject'>Reject</button>
    </form>
    """
    return render_page("Review Price Range", body)


@app.post("/officer/prices/{price_id}/review")
def review_price(
    price_id: int,
    request: Request,
    action: str = Form(...),
    note: str = Form(""),
) -> RedirectResponse:
    officer = require_officer(request)
    if action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="Invalid review action")
    with connect() as conn:
        row = conn.execute("SELECT * FROM price_records WHERE id=?", (price_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Price record not found")
        if row["submitted_by"] == officer["officer_id"]:
            log_audit(officer["officer_id"], "self_approval_blocked", "PriceRecord", price_id)
            raise HTTPException(status_code=403, detail="Self-approval is blocked")
        status = "approved" if action == "approve" else "rejected"
        now = iso_now()
        conn.execute(
            """
            UPDATE price_records
            SET status=?, reviewed_by=?, review_note=?, updated_at=?, reviewed_at=?
            WHERE id=?
            """,
            (status, officer["officer_id"], note, now, now, price_id),
        )
    log_audit(officer["officer_id"], f"{status}_price_range", "PriceRecord", price_id, note)
    return RedirectResponse("/officer/prices", status_code=303)


@app.get("/officer/audit", response_class=HTMLResponse)
def audit(request: Request, format: str = "html") -> Response:
    require_officer(request)
    with connect() as conn:
        rows = conn.execute("SELECT * FROM audit_events ORDER BY id DESC").fetchall()
    if format == "csv":
        out = StringIO()
        writer = csv.writer(out)
        writer.writerow(["id", "actor_id", "action", "entity_type", "entity_id", "details", "created_at"])
        for row in rows:
            writer.writerow([row["id"], row["actor_id"], row["action"], row["entity_type"], row["entity_id"], row["details"], row["created_at"]])
        return Response(out.getvalue(), media_type="text/csv")
    table = "".join(
        f"<tr><td>{row['created_at'][:19]}</td><td>{row['actor_id']}</td><td>{row['action']}</td><td>{row['entity_type']}</td></tr>"
        for row in rows
    )
    return render_page("Audit Trail", f"<p><a href='/officer/audit?format=csv'>CSV export</a></p><table>{table}</table>")


@app.get("/officer/metrics", response_class=HTMLResponse)
def metrics(request: Request) -> HTMLResponse:
    require_officer(request)
    with connect() as conn:
        channels = conn.execute("SELECT channel, response_state, COUNT(*) AS n FROM farmer_queries GROUP BY channel, response_state").fetchall()
        flags = conn.execute("SELECT flag, COUNT(*) AS n FROM guardian_flags GROUP BY flag").fetchall()
    channel_rows = "".join(f"<tr><td>{r['channel']}</td><td>{r['response_state']}</td><td>{r['n']}</td></tr>" for r in channels)
    flag_rows = "".join(f"<tr><td>{r['flag']}</td><td>{r['n']}</td></tr>" for r in flags)
    body = (
        "<h2>Channel metrics</h2><table><tr><th>Channel</th><th>State</th><th>Queries</th></tr>"
        f"{channel_rows or '<tr><td colspan=3>No channel queries yet.</td></tr>'}</table>"
        "<h2>Guardian flags</h2><table><tr><th>Flag</th><th>Count</th></tr>"
        f"{flag_rows or '<tr><td colspan=2>No flags yet.</td></tr>'}</table>"
    )
    return render_page("Metrics", body)


@app.get("/channels/demo", response_class=HTMLResponse)
def channels_demo() -> HTMLResponse:
    body = """
    <section class='grid'>
      <form method='post' action='/channels/sms/inbound'>
        <h2>SMS simulator</h2>
        <label>From</label><br><input name='from' value='+255700123456'><br>
        <label>Text</label><br><input name='text' value='MAHINDI'><br>
        <button>Send SMS query</button>
      </form>
      <form method='post' action='/channels/ussd/callback'>
        <h2>USSD simulator</h2>
        <label>Session</label><br><input name='sessionId' value='demo-session'><br>
        <label>Service code</label><br><input name='serviceCode' value='*700#'><br>
        <label>Phone</label><br><input name='phoneNumber' value='+255700123456'><br>
        <label>Text</label><br><input name='text' value=''><br>
        <button>Send USSD step</button>
      </form>
    </section>
    <p>Use blank USSD text for the menu, then text 1, 2, 3, or 4 for selections.</p>
    """
    return render_page("Basic Phone Channel Simulator", body)


@app.post("/channels/ussd/callback", response_class=PlainTextResponse)
async def ussd_callback(request: Request) -> PlainTextResponse:
    init_db()
    form = await request.form()
    session_id = str(form.get("sessionId", ""))
    phone = str(form.get("phoneNumber", ""))
    text = str(form.get("text", "")).strip()
    if text == "":
        log_query("ussd", None, "menu", phone=phone, session_id=session_id)
        return PlainTextResponse("CON Karibu MarketLink\n1. Bei ya mahindi\n2. Bei ya alizeti\n3. Bei ya karanga\n4. Msaada")
    if text in USSD_SELECTIONS:
        crop = USSD_SELECTIONS[text]
        state, message = price_message(crop, lang="sw", channel="ussd")
        log_query("ussd", crop, state, phone=phone, session_id=session_id)
        return PlainTextResponse(f"END {message}")
    if text == "4":
        log_query("ussd", None, "help", phone=phone, session_id=session_id)
        return PlainTextResponse("END Kwa msaada piga *700# au wasiliana na afisa wa soko.")
    log_query("ussd", None, "invalid", phone=phone, session_id=session_id)
    return PlainTextResponse("END Chaguo si sahihi. Tafadhali jaribu tena.")


class SmsSendResult(dict):
    pass


class MockSmsProvider:
    name = "mock"

    def send(self, to: str, message: str) -> SmsSendResult:
        return SmsSendResult(provider=self.name, status="mocked", to=mask_phone(to), message=message)


class AfricasTalkingSmsProvider:
    name = "africastalking"

    def send(self, to: str, message: str) -> SmsSendResult:
        if not live_sms_enabled():
            return SmsSendResult(provider=self.name, status="disabled", to=mask_phone(to), message=message)
        return SmsSendResult(provider=self.name, status="ready_for_sdk", to=mask_phone(to), message=message)


def live_sms_enabled() -> bool:
    return (
        os.getenv("SMS_PROVIDER", "mock").lower() == "africastalking"
        and os.getenv("AT_USERNAME") is not None
        and os.getenv("AT_API_KEY") is not None
        and os.getenv("ENABLE_LIVE_SMS", "false").lower() == "true"
    )


def sms_provider() -> MockSmsProvider | AfricasTalkingSmsProvider:
    if os.getenv("SMS_PROVIDER", "mock").lower() == "africastalking":
        return AfricasTalkingSmsProvider()
    return MockSmsProvider()


def parse_sms_keyword(text: str) -> str | None:
    tokens = [token.strip(" .,!?:;").upper() for token in text.split()]
    for token in tokens:
        if token in SMS_KEYWORDS:
            return SMS_KEYWORDS[token]
    return None


@app.post("/channels/sms/inbound")
async def sms_inbound(request: Request) -> JSONResponse:
    init_db()
    form = await request.form()
    sender = str(form.get("from", ""))
    text = str(form.get("text", ""))
    normalized = text.strip().upper()
    if normalized in {"MSAADA", "HELP"}:
        log_query("sms", None, "help", phone=sender)
        message = "Tuma MAHINDI, ALIZETI, au KARANGA kupata bei ya rejea. Send MAIZE, SUNFLOWER, or GROUNDNUTS."
    else:
        crop = parse_sms_keyword(text)
        if crop is None:
            log_query("sms", None, "invalid", phone=sender)
            message = "Tuma MAHINDI, ALIZETI, au KARANGA. Bei ni rejea tu, si ahadi ya mnunuzi."
        else:
            state, message = price_message(crop, lang="sw", channel="sms")
            log_query("sms", crop, state, phone=sender)
    result = sms_provider().send(sender, message)
    return JSONResponse({"message": message, "provider": result})


@app.post("/channels/sms/delivery-report")
async def sms_delivery_report(request: Request) -> dict[str, str]:
    form = await request.form()
    phone = str(form.get("phoneNumber") or form.get("to") or "")
    status = str(form.get("status") or form.get("deliveryStatus") or "unknown")
    provider = str(form.get("provider") or os.getenv("SMS_PROVIDER", "mock"))
    message_id = str(form.get("id") or form.get("messageId") or "")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO channel_delivery_events (provider, message_id, status, masked_phone, raw_state, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (provider, message_id, status, mask_phone(phone), status, iso_now()),
        )
    return {"status": "received"}


@app.get("/agent-demo", response_class=HTMLResponse)
def agent_demo() -> HTMLResponse:
    with connect() as conn:
        cases = conn.execute("SELECT * FROM agent_demo_cases ORDER BY id DESC LIMIT 10").fetchall()
    rows = "".join(
        f"<tr><td>{c['id']}</td><td>{c['crop']}</td><td>{c['offered_price']}</td><td>{c['status']}</td>"
        f"<td><form method='post' action='/agent-demo/{c['id']}/review'><input name='reviewer_id' value='human-reviewer'>"
        "<select name='decision'><option value='needs_support'>Needs support</option><option value='resolved'>Resolved</option></select>"
        "<button>Record review</button></form></td></tr>"
        for c in cases
    )
    body = f"""
    <form method='post' action='/agent-demo'>
      <h2>Scout -> Guardian -> Hunter</h2>
      <label>Crop</label><br><select name='crop'>{crop_options()}</select><br>
      <label>Offered price TZS/kg</label><br><input name='offered_price' type='number' value='500'><br>
      <label>Quantity kg</label><br><input name='quantity_kg' type='number' value='100'><br>
      <label>Scale ID state</label><br><select name='scale_id_state'><option value='present'>present</option><option value='missing'>missing</option></select><br>
      <label>Payment state</label><br><select name='payment_state'><option value='paid'>paid</option><option value='delayed'>delayed</option><option value='disputed'>disputed</option></select><br>
      <label>Buyer/broker record state</label><br><select name='actor_record_state'><option value='present'>present</option><option value='missing'>missing</option></select><br>
      <button>Run synthetic case</button>
    </form>
    <h2>Recent cases</h2><table><tr><th>ID</th><th>Crop</th><th>Offer</th><th>Status</th><th>Human review</th></tr>{rows}</table>
    """
    return render_page("Agent Savannah Demo", body)


def guardian_flags(crop: str, offered_price: int, scale_id_state: str, payment_state: str, actor_record_state: str) -> tuple[list[str], dict[str, Any]]:
    state = price_state(crop)
    record = state["record"]
    flags: list[str] = []
    if record and offered_price < int(record["min_price"]):
        flags.append("offer_below_reference_range")
    if scale_id_state == "missing":
        flags.append("missing_scale_id")
    if actor_record_state == "missing":
        flags.append("missing_actor_record")
    if payment_state == "delayed":
        flags.append("payment_delayed")
    if payment_state == "disputed":
        flags.append("payment_disputed")
    return flags, state


def hunter_briefing(case_id: int, crop: str, offered_price: int, quantity_kg: int, flags: list[str], state: dict[str, Any]) -> str:
    record = state["record"]
    reference = "no approved reference range" if record is None else f"{record['min_price']}-{record['max_price']} {record['unit']}"
    return (
        f"Case {case_id}: Scout retrieved {reference} for {crop}. Guardian flagged {', '.join(flags)}. "
        f"Facts: offered price {offered_price}, quantity {quantity_kg} kg. Missing evidence or disputed payment requires human review. "
        "No automatic punishment, blacklisting, or fraud accusation is applied."
    )


@app.post("/agent-demo")
def create_agent_case(
    crop: str = Form(...),
    offered_price: int = Form(...),
    quantity_kg: int = Form(...),
    scale_id_state: str = Form(...),
    payment_state: str = Form(...),
    actor_record_state: str = Form(...),
) -> RedirectResponse:
    if crop not in CROPS:
        raise HTTPException(status_code=400, detail="Unsupported crop")
    flags, state = guardian_flags(crop, offered_price, scale_id_state, payment_state, actor_record_state)
    record = state["record"]
    status = "human_review_required" if flags else "clean_no_action"
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO agent_demo_cases
            (crop, offered_price, quantity_kg, scale_id_state, payment_state, actor_record_state, reference_min, reference_max, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                crop,
                offered_price,
                quantity_kg,
                scale_id_state,
                payment_state,
                actor_record_state,
                record["min_price"] if record else None,
                record["max_price"] if record else None,
                status,
                iso_now(),
            ),
        )
        case_id = cursor.lastrowid
        for flag in flags:
            conn.execute("INSERT INTO guardian_flags (case_id, flag, created_at) VALUES (?, ?, ?)", (case_id, flag, iso_now()))
        if flags:
            briefing = hunter_briefing(case_id, crop, offered_price, quantity_kg, flags, state)
            conn.execute("INSERT INTO hunter_briefings (case_id, briefing, created_at) VALUES (?, ?, ?)", (case_id, briefing, iso_now()))
    log_audit("agent-demo", "synthetic_case_created", "AgentDemoCase", case_id, status)
    return RedirectResponse("/agent-demo", status_code=303)


@app.post("/agent-demo/{case_id}/review")
def review_agent_case(
    case_id: int,
    reviewer_id: str = Form("human-reviewer"),
    decision: str = Form(...),
    note: str = Form(""),
) -> RedirectResponse:
    with connect() as conn:
        case = conn.execute("SELECT * FROM agent_demo_cases WHERE id=?", (case_id,)).fetchone()
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        conn.execute(
            "INSERT INTO human_review_decisions (case_id, reviewer_id, decision, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (case_id, reviewer_id, decision, note, iso_now()),
        )
        conn.execute("UPDATE agent_demo_cases SET status=? WHERE id=?", (f"reviewed_{decision}", case_id))
    log_audit(reviewer_id, "human_review_decision", "AgentDemoCase", case_id, decision)
    return RedirectResponse("/agent-demo", status_code=303)


@app.get("/offline.html", response_class=HTMLResponse)
def offline() -> HTMLResponse:
    body = """
    <h2>Offline</h2>
    <p>MarketLink is offline. Previously loaded public pages may be available.</p>
    <p>For basic phones, use the SMS or USSD channel once connectivity is available.</p>
    """
    return render_page("MarketLink Offline", body, lite=True)


@app.get("/manifest.webmanifest")
def manifest() -> JSONResponse:
    return JSONResponse(
        {
            "name": APP_NAME,
            "short_name": "MarketLink",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#f7f8f3",
            "theme_color": "#244b35",
            "icons": [],
        },
        media_type="application/manifest+json",
    )


@app.get("/service-worker.js", response_class=PlainTextResponse)
def service_worker() -> PlainTextResponse:
    js = """
const CACHE = 'marketlink-public-v1';
const SAFE = ['/', '/lite', '/market', '/offline.html', '/manifest.webmanifest'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SAFE)));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/officer') || url.pathname.startsWith('/api') || url.pathname.startsWith('/channels')) return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request).then(r => r || caches.match('/offline.html'))));
});
"""
    return PlainTextResponse(js.strip(), media_type="application/javascript")


def seed_demo_data() -> None:
    reset_database()
    now = iso_now()
    stale = (utcnow() - timedelta(hours=freshness_hours() + 4)).isoformat()
    rows = [
        ("maize", 650, 780, "Kibaigwa market officer", now),
        ("sunflower", 1100, 1280, "Kibaigwa market officer", now),
        ("groundnuts", 1800, 2100, "Kibaigwa market officer", stale),
    ]
    with connect() as conn:
        for crop, min_price, max_price, source, reviewed_at in rows:
            conn.execute(
                """
                INSERT INTO price_records
                (crop, min_price, max_price, source, status, submitted_by, reviewed_by, created_at, updated_at, reviewed_at)
                VALUES (?, ?, ?, ?, 'approved', 'OFFICER-A', 'OFFICER-B', ?, ?, ?)
                """,
                (crop, min_price, max_price, source, reviewed_at, reviewed_at, reviewed_at),
            )
    log_audit("seed", "seed_demo_data", "PriceRecord", None, "maize,sunflower,groundnuts")
    print("Seeded demo data for maize, sunflower, and groundnuts.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "seed-demo":
        seed_demo_data()
    else:
        print("Usage: python -m app.main seed-demo")
