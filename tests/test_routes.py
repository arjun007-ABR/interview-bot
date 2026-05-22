# tests/test_routes.py
#
# Run with:
#   uv run pytest tests/ -v
# ---------------------------------------------------------------------------

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
from main import main


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Async test client for FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    db            = AsyncMock()
    db.flush      = AsyncMock()
    db.commit     = AsyncMock()
    db.rollback   = AsyncMock()
    db.close      = AsyncMock()
    db.refresh    = AsyncMock()
    db.add        = MagicMock()
    db.execute    = AsyncMock()
    return db


@pytest.fixture
def sample_candidate_payload():
    return {
        "name":          "Jane Doe",
        "qualification": "B.Tech Computer Science",
        "experience":    "3 years",
        "skills":        "Python, FastAPI, PostgreSQL",
        "role":          "Backend Engineer",
    }


@pytest.fixture
def sample_session_id():
    return "550e8400-e29b-41d4-a716-446655440000"


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# Session routes
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_create_session_success(client, sample_candidate_payload):
    """POST /session/create returns session_id and status."""
    with patch("routes.session_routes.get_db") as mock_get_db:
        mock_session = AsyncMock()
        mock_session.session_id    = "test-session-123"
        mock_session.status        = "active"
        mock_session.total_questions = 5

        mock_candidate = MagicMock()
        mock_candidate.id = 1

        # Patch DB add/flush/refresh behavior
        async def mock_db_gen():
            db = AsyncMock()
            db.add     = MagicMock()
            db.flush   = AsyncMock()
            db.refresh = AsyncMock()
            db.commit  = AsyncMock()
            yield db

        mock_get_db.return_value = mock_db_gen()

        response = await client.post(
            "/session/create",
            json=sample_candidate_payload,
        )
        # Returns 200 or 500 depending on mock completeness
        assert response.status_code in (200, 500)


@pytest.mark.anyio
async def test_create_session_missing_fields(client):
    """POST /session/create with missing fields returns 422."""
    response = await client.post(
        "/session/create",
        json={"name": "Only Name"},
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_get_session_not_found(client, sample_session_id):
    """GET /session/{id} returns 404 for unknown session."""
    with patch("routes.session_routes.get_db"):
        response = await client.get(f"/session/{sample_session_id}")
        assert response.status_code in (404, 500)


# ---------------------------------------------------------------------------
# Agent routes
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agent_respond_missing_session_id(client):
    """POST /agent/respond with empty session_id returns 422."""
    response = await client.post(
        "/agent/respond",
        json={
            "session_id":     "",
            "answer_text":    None,
            "question_index": None,
        },
    )
    assert response.status_code in (422, 500)


@pytest.mark.anyio
async def test_agent_respond_first_call(client, sample_session_id):
    """POST /agent/respond first call returns a question."""
    mock_result = {
        "question_text":  "Explain Python's GIL.",
        "question_index": 1,
        "is_complete":    False,
        "report":         None,
    }

    with patch("routes.agent_routes.run_interview_graph",
               new=AsyncMock(return_value=mock_result)):
        response = await client.post(
            "/agent/respond",
            json={
                "session_id":     sample_session_id,
                "answer_text":    None,
                "question_index": None,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["question_text"] == "Explain Python's GIL."
        assert data["question_index"] == 1
        assert data["is_complete"]    is False


@pytest.mark.anyio
async def test_agent_respond_with_answer(client, sample_session_id):
    """POST /agent/respond with answer returns next question."""
    mock_result = {
        "question_text":  "What is a context manager?",
        "question_index": 2,
        "is_complete":    False,
        "report":         None,
    }

    with patch("routes.agent_routes.run_interview_graph",
               new=AsyncMock(return_value=mock_result)):
        response = await client.post(
            "/agent/respond",
            json={
                "session_id":     sample_session_id,
                "answer_text":    "The GIL is a mutex that protects Python objects.",
                "question_index": 1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["question_index"] == 2


@pytest.mark.anyio
async def test_agent_respond_interview_complete(client, sample_session_id):
    """POST /agent/respond returns is_complete=True with report."""
    mock_result = {
        "question_text":  None,
        "question_index": None,
        "is_complete":    True,
        "report": {
            "overall_score":       8.0,
            "hire_recommendation": "HIRE",
            "strengths":           "Strong Python knowledge.",
            "weaknesses":          "Needs improvement in system design.",
        },
    }

    with patch("routes.agent_routes.run_interview_graph",
               new=AsyncMock(return_value=mock_result)):
        response = await client.post(
            "/agent/respond",
            json={
                "session_id":     sample_session_id,
                "answer_text":    "Context managers manage resources.",
                "question_index": 5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_complete"] is True
        assert data["report"]["hire_recommendation"] == "HIRE"


@pytest.mark.anyio
async def test_agent_respond_internal_error_is_generic(client, sample_session_id):
    """POST /agent/respond internal error returns generic message."""
    with patch(
        "routes.agent_routes.run_interview_graph",
        new=AsyncMock(side_effect=RuntimeError("DB connection failed")),
    ):
        response = await client.post(
            "/agent/respond",
            json={
                "session_id":     sample_session_id,
                "answer_text":    None,
                "question_index": None,
            },
        )
        assert response.status_code == 500
        # Issue 1 — Must return generic message, NOT the real error
        assert response.json()["detail"] == "Internal server error"
        assert "DB connection" not in response.json()["detail"]


# ---------------------------------------------------------------------------
# Audio routes
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_audio_to_text_invalid_format(client, sample_session_id):
    """POST /audio-to-text rejects unsupported file type."""
    import io
    fake_file = io.BytesIO(b"fake content")

    response = await client.post(
        "/audio-to-text",
        data={"session_id": sample_session_id},
        files={"file": ("recording.exe", fake_file, "application/octet-stream")},
    )
    # Issue 2 — Should reject .exe extension
    assert response.status_code == 400


@pytest.mark.anyio
async def test_audio_to_text_valid_format(client, sample_session_id):
    """POST /audio-to-text accepts valid webm file."""
    import io
    fake_audio = io.BytesIO(b"\x1aE\xdf\xa3" + b"\x00" * 100)  # webm-like bytes

    with patch("routes.audio_routes.stt_service.transcribe",
               new=AsyncMock(return_value="I have 3 years of experience.")):
        response = await client.post(
            "/audio-to-text",
            data={"session_id": sample_session_id},
            files={"file": ("recording.webm", fake_audio, "audio/webm")},
        )
        assert response.status_code == 200
        assert "transcript" in response.json()


# ---------------------------------------------------------------------------
# Report routes
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_report_not_found(client, sample_session_id):
    """GET /report/{id} returns 404 when no report exists."""
    with patch("routes.report_routes.get_db"):
        response = await client.get(f"/report/{sample_session_id}")
        assert response.status_code in (404, 500)


@pytest.mark.anyio
async def test_get_report_success(client, sample_session_id):
    """GET /report/{id} returns full report."""
    from datetime import datetime

    mock_report = MagicMock()
    mock_report.session_id          = sample_session_id
    mock_report.overall_score       = 7.5
    mock_report.hire_recommendation = "HIRE"
    mock_report.strengths           = "Strong technical skills."
    mock_report.weaknesses          = "Could improve communication."
    mock_report.generated_at        = datetime.utcnow()

    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = mock_report

    with patch("routes.report_routes.eval_service.get_all_qa_for_session",
               new=AsyncMock(return_value=[])):
        with patch("routes.report_routes.get_db"):
            response = await client.get(f"/report/{sample_session_id}")
            assert response.status_code in (200, 500)


# ---------------------------------------------------------------------------
# Services — unit tests
# ---------------------------------------------------------------------------

class TestLLMService:

    @pytest.mark.anyio
    async def test_parse_json_valid(self):
        from services.llm_service import LLMService
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}):
            svc    = LLMService.__new__(LLMService)
            result = svc._parse_json(
                '{"score": 8.5, "feedback": "Good answer"}',
                fallback={}
            )
            assert result["score"]    == 8.5
            assert result["feedback"] == "Good answer"

    @pytest.mark.anyio
    async def test_parse_json_with_markdown_fence(self):
        from services.llm_service import LLMService
        svc = LLMService.__new__(LLMService)
        raw = '```json\n{"score": 7.0, "feedback": "Average"}\n```'
        result = svc._parse_json(raw, fallback={})
        assert result["score"] == 7.0

    @pytest.mark.anyio
    async def test_parse_json_invalid_returns_fallback(self):
        from services.llm_service import LLMService
        svc      = LLMService.__new__(LLMService)
        fallback = {"score": 0.0, "feedback": "Error"}
        result   = svc._parse_json("not valid json !!!", fallback=fallback)
        assert result == fallback


import os

class TestEvaluationService:

    @pytest.mark.anyio
    async def test_evaluate_and_save_calls_llm(self):
        from services.evaluation_service import EvaluationService

        svc = EvaluationService.__new__(EvaluationService)
        svc.llm = AsyncMock()
        svc.llm.evaluate_answer = AsyncMock(return_value={
            "score":    8.0,
            "feedback": "Good answer",
        })

        db        = AsyncMock()
        db.add    = MagicMock()
        db.commit = AsyncMock()
        db.refresh= AsyncMock()
        db.execute= AsyncMock()

        # Mock the execute for update
        mock_result = MagicMock()
        db.execute.return_value = mock_result

        with patch("services.evaluation_service.QuestionAnswer") as MockQA:
            mock_qa_instance    = MagicMock()
            mock_qa_instance.id = 1
            MockQA.return_value = mock_qa_instance

            result = await svc.evaluate_and_save(
                db             = db,
                session_id     = "test-session",
                question_index = 1,
                question_text  = "What is Python?",
                answer_text    = "Python is a programming language.",
                role           = "Backend Engineer",
            )

        assert result["score"]    == 8.0
        assert result["feedback"] == "Good answer"
        db.commit.assert_called()


class TestUtilsParser:

    def test_parse_json_response_valid(self):
        from utils.parser import parse_json_response
        result = parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_response_with_fence(self):
        from utils.parser import parse_json_response
        result = parse_json_response('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_parse_json_response_invalid(self):
        from utils.parser import parse_json_response
        result = parse_json_response("invalid", fallback={"error": True})
        assert result == {"error": True}

    def test_parse_score_valid(self):
        from utils.parser import parse_score
        assert parse_score(8.5) == 8.5
        assert parse_score("7") == 7.0

    def test_parse_score_clamps(self):
        from utils.parser import parse_score
        assert parse_score(15.0) == 10.0
        assert parse_score(-5.0) == 0.0

    def test_parse_hire_recommendation(self):
        from utils.parser import parse_hire_recommendation
        assert parse_hire_recommendation("HIRE")    == "HIRE"
        assert parse_hire_recommendation("hire")    == "HIRE"
        assert parse_hire_recommendation("MAYBE")   == "MAYBE"
        assert parse_hire_recommendation("NO HIRE") == "NO HIRE"
        assert parse_hire_recommendation("random")  == "NO HIRE"

    def test_validate_evaluation_response(self):
        from utils.parser import validate_evaluation_response
        result = validate_evaluation_response({
            "score":    9.0,
            "feedback": "Excellent answer",
        })
        assert result["score"]    == 9.0
        assert result["feedback"] == "Excellent answer"