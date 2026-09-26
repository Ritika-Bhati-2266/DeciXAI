import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

def test_health_check():
    """Test the new health check endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "uptime_seconds" in data
    assert "models" in data
    assert "career" in data["models"]

def test_root_endpoint():
    """Test the root endpoint for backwards compatibility/info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data

def test_api_key_auth_enforcement(monkeypatch):
    """Test that API Key middleware blocks unauthorized requests when configured."""
    monkeypatch.setattr("middleware.security.API_KEY", "test-secret-key")
    
    # Root and health should bypass auth
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    # Without API key, career parse should fail
    response = client.post("/api/v1/career/parse", json={"text": "I want to be a data scientist"})
    assert response.status_code == 401
    
    # With wrong API key, should fail
    response = client.post(
        "/api/v1/career/parse", 
        json={"text": "I want to be a data scientist"},
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 401

    # With correct API key, should pass (or return 200/400 depending on actual service behavior)
    response = client.post(
        "/api/v1/career/parse", 
        json={"text": "I want to be a data scientist"},
        headers={"X-API-Key": "test-secret-key"}
    )
    assert response.status_code in (200, 422)

def test_cors_headers():
    """Test that CORS headers are appropriately applied."""
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert response.status_code == 200
    # Depending on how CORSMiddleware is set up, verify headers:
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

def test_rate_limiter(monkeypatch):
    """Test that the sliding window rate limiter kicks in."""
    from middleware.rate_limiter import _counter
    _counter._hits.clear()
    # Temporarily set limit to 2
    monkeypatch.setattr("middleware.rate_limiter.RATE_LIMIT", 2)
    
    # 1st request
    r1 = client.get("/api/v1/health")
    assert r1.status_code == 200
    
    # 2nd request
    r2 = client.get("/api/v1/health")
    assert r2.status_code == 200
    
    # 3rd request should hit limit
    r3 = client.get("/api/v1/health")
    assert r3.status_code == 429
    assert r3.json()["detail"] == "Too many requests. Please slow down."


def test_resume_upload_pdf():
    """Test resume upload endpoint with a generated PDF byte stream."""
    import io
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer)
    p.drawString(100, 750, "Jane Doe - Full Stack AI Developer")
    p.drawString(100, 730, "Education: B.Tech Computer Science, CGPA 8.9")
    p.drawString(100, 710, "Skills: Python, FastAPI, React, Docker, SQL, Machine Learning")
    p.drawString(100, 690, "Experience: Built scalable inference backend handling 50k requests/day")
    p.drawString(100, 670, "Projects: Autonomous RAG Copilot with 40% accuracy improvement")
    p.drawString(100, 650, "Certifications: AWS Certified Machine Learning Specialty")
    p.showPage()
    p.save()

    pdf_bytes = buffer.getvalue()
    files = {"file": ("test_resume.pdf", pdf_bytes, "application/pdf")}
    response = client.post("/api/v1/career/upload-resume", files=files)
    assert response.status_code == 200
    data = response.json()
    assert "ats_audit" in data
    assert "ats_score" in data["ats_audit"]
    assert data["ats_audit"]["ats_score"] > 0
    assert "parsed_profile" in data
    assert "decision" in data
    assert "decision" in data["decision"]


def _startup_roadmap_of(result):
    """Helper: extract the deterministic startup roadmap from a decision payload."""
    details = result.get("details") or {}
    roadmap = details.get("startup_roadmap") or {}
    assert isinstance(roadmap, dict), "startup_roadmap missing from response details"
    return roadmap


def test_startup_roadmap_investor_ready():
    """High-score venture should reach Investor-ready/Seed-ready with a full 4-phase roadmap."""
    from services.startup_service import get_startup_decision

    result = get_startup_decision({
        "funding": 500000,
        "team_size": 6,
        "market": "B2B SaaS",
        "experience": 6,
    })
    roadmap = _startup_roadmap_of(result)
    assert roadmap.get("stage") in ("Investor-ready", "Seed-ready")
    assert len(roadmap.get("phases") or []) == 4
    for phase in roadmap["phases"]:
        assert phase.get("phase") and phase.get("timeline")
        assert len(phase.get("tasks") or []) >= 3
        assert phase.get("exit_criteria")
    assert "risk_flags" in roadmap and isinstance(roadmap["risk_flags"], list)
    # Well-funded team should have no critical blockers
    assert roadmap["risk_flags"] == []


def test_startup_roadmap_idea_validation():
    """Low-score venture should land in Idea-validation/Pre-seed with critical blockers flagged."""
    from services.startup_service import get_startup_decision

    result = get_startup_decision({
        "funding": 25000,
        "team_size": 2,
        "market": "Consumer Productivity",
        "experience": 1,
    })
    roadmap = _startup_roadmap_of(result)
    assert roadmap.get("stage") in ("Idea-validation", "Pre-seed")
    assert len(roadmap.get("phases") or []) == 4
    assert len(roadmap.get("risk_flags") or []) >= 2
    blob = " ".join(roadmap["risk_flags"]).lower()
    assert "runway" in blob or "capital" in blob
    # Last phase should be runway-extension, not a fundraise push
    assert roadmap["phases"][-1]["phase"] == "Extend runway"


def test_startup_roadmap_zero_inputs_no_crash():
    """Edge case: funding=0 / team_size=0 must not crash and must flag critical risk."""
    from services.startup_service import _build_startup_roadmap

    roadmap = _build_startup_roadmap(0, 0, "", 0, 10.0, market_type="general", market_segment="")
    assert roadmap.get("stage") == "Idea-validation"
    assert len(roadmap.get("phases") or []) == 4
    assert len(roadmap.get("risk_flags") or []) >= 2
    assert roadmap.get("runway_months") == 0.0


def test_roadmap_unicode_print_safe():
    """Roadmap text contains non-cp1252 symbols (>=, em-dash); printing/logging must not crash on Windows."""
    import io
    import json
    import sys
    from services.startup_service import get_startup_decision

    result = get_startup_decision({
        "funding": 25000,
        "team_size": 2,
        "market": "Consumer Productivity",
        "experience": 1,
    })
    payload = json.dumps(result, ensure_ascii=False)
    assert any(sym in payload for sym in (">=", "\u2014", "\u2192")) or "CRITICAL" in payload

    # Simulate a cp1252-limited terminal: writing symbols must raise there,
    # proving the test exercises the real encoding path...
    strict_buf = io.BytesIO()
    strict_stream = io.TextIOWrapper(strict_buf, encoding="cp1252", errors="strict")
    try:
        with strict_stream:
            strict_stream.write("exit gate \u2265 test")
        raised = False
    except UnicodeEncodeError:
        raised = True
    assert raised, "sanity check: cp1252 stream should reject the roadmap symbol"

    # ...while the app-configured stdout must accept it without raising.
    print(payload[:1000])
    if sys.platform == "win32":
        encoding = (sys.stdout.encoding or "").lower().replace("-", "")
        assert encoding == "utf8", f"stdout not UTF-8 on Windows: {sys.stdout.encoding}"

    # PDF pipeline must also digest the same symbols without error.
    from services.pdf_service import generate_decision_report
    buf = generate_decision_report("startup", result)
    assert len(buf.getvalue()) > 0


def test_startup_parse_lakh_crore():
    """Free-text funding in Indian units must parse to full amounts (no NaN)."""
    from services.startup_service import parse_startup_input

    assert parse_startup_input("funding 20 lakh, team 4, experience 2 years")["funding"] == 2_000_000.0
    assert parse_startup_input("raised 2.5 crore, team 6, experience 5 years")["funding"] == 25_000_000.0
    assert parse_startup_input("funding 50L, team 5, experience 3 years")["funding"] == 5_000_000.0


def test_startup_input_bounds():
    """Absurd values must be rejected at the schema layer."""
    from pydantic import ValidationError

    from models.schemas import StartupInput

    StartupInput(funding=300000, team_size=5, market="B2B SaaS", experience=4)
    # Exact boundary values must remain valid.
    StartupInput(funding=100_000_000_000.0, team_size=10_000, market="x", experience=60.0)
    for bad in [
        {"funding": 1e15, "team_size": 5, "market": "x", "experience": 4},
        {"funding": 100_000_000_000.0 + 1, "team_size": 5, "market": "x", "experience": 4},
        {"funding": 100, "team_size": 0, "market": "x", "experience": 4},
        {"funding": 100, "team_size": 5, "market": "", "experience": 4},
    ]:
        try:
            StartupInput(**bad)
        except ValidationError:
            continue
        raise AssertionError(f"should have rejected {bad}")


def test_finance_input_bounds():
    """Absurd values must be rejected at the schema layer."""
    from pydantic import ValidationError

    from models.schemas import FinanceInput

    FinanceInput(income=75000, loan=18000, credit_score=710)
    # Exact boundary values must remain valid.
    FinanceInput(income=100_000_000_000.0, loan=100_000_000_000.0, credit_score=850.0)
    for bad in [
        {"income": 1e15, "loan": 18000, "credit_score": 710},
        {"income": 75000, "loan": 100_000_000_000.0 + 1, "credit_score": 710},
        {"income": 0, "loan": 18000, "credit_score": 710},
        {"income": 75000, "loan": -1, "credit_score": 710},
        {"income": 75000, "loan": 18000, "credit_score": 900},
    ]:
        try:
            FinanceInput(**bad)
        except ValidationError:
            continue
        raise AssertionError(f"should have rejected {bad}")


def test_policy_input_bounds():
    """Absurd values must be rejected at the schema layer."""
    from pydantic import ValidationError

    from models.schemas import PolicyInput

    PolicyInput(sector="education", budget=5000000, population=1200000)
    # Exact boundary values must remain valid.
    PolicyInput(sector="x", budget=1_000_000_000_000.0, population=10_000_000_000.0)
    for bad in [
        {"sector": "education", "budget": 1e18, "population": 1200000},
        {"sector": "education", "budget": 5000000, "population": 1e15},
        {"sector": "", "budget": 5000000, "population": 1200000},
        {"sector": "education", "budget": -1, "population": 1200000},
        {"sector": "education", "budget": 5000000, "population": -5},
    ]:
        try:
            PolicyInput(**bad)
        except ValidationError:
            continue
        raise AssertionError(f"should have rejected {bad}")


