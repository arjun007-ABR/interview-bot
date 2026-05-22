// scripts/api.js
// Issue 3 + 5 — Use relative URLs instead of hardcoded localhost.
// When FastAPI serves the HTML, all API calls go to the same origin
// automatically — no CORS issues, no hardcoded ports.

// ---------------------------------------------------------------------------
// Base URL — auto-detects environment
// ---------------------------------------------------------------------------
const API_BASE = (() => {
    // If opened via file:// (direct file open) fall back to localhost
    if (window.location.protocol === "file:") {
        return "http://localhost:8000";
    }
    // When served by FastAPI — same origin, no prefix needed
    return "";
})();

console.log(`[API] Base URL: '${API_BASE || "(same origin)"}'`);

// ---------------------------------------------------------------------------
// Internal fetch wrapper
// ---------------------------------------------------------------------------
async function apiFetch(method, path, body = null, isFormData = false) {
    const headers = isFormData ? {} : { "Content-Type": "application/json" };

    const options = {
        method,
        headers,
        body: body
            ? isFormData
                ? body
                : JSON.stringify(body)
            : undefined,
    };

    let response;
    try {
        response = await fetch(`${API_BASE}${path}`, options);
    } catch (networkErr) {
        console.error(`[API] Network error | ${method} ${path}`, networkErr);
        throw new Error(
            "Cannot reach the server. Make sure the backend is running."
        );
    }

    if (!response.ok) {
        let detail = `Request failed (${response.status})`;
        try {
            const err = await response.json();
            detail    = err.detail || detail;
        } catch (_) {}
        console.error(`[API] ${response.status} | ${method} ${path} | ${detail}`);
        throw new Error(detail);
    }

    return response.json();
}

// ---------------------------------------------------------------------------
// Session
// ---------------------------------------------------------------------------
async function createSession(candidateData) {
    return apiFetch("POST", "/session/create", candidateData);
}

async function getSession(sessionId) {
    return apiFetch("GET", `/session/${sessionId}`);
}

// ---------------------------------------------------------------------------
// Agent
// ---------------------------------------------------------------------------
async function agentRespond(sessionId, answerText, questionIndex) {
    return apiFetch("POST", "/agent/respond", {
        session_id:     sessionId,
        answer_text:    answerText    ?? null,
        question_index: questionIndex ?? null,
    });
}

// ---------------------------------------------------------------------------
// Audio
// ---------------------------------------------------------------------------
async function audioToText(audioBlob, sessionId) {
    const formData = new FormData();
    formData.append("file",       audioBlob, "recording.webm");
    formData.append("session_id", sessionId);
    return apiFetch("POST", "/audio-to-text", formData, true);
}

async function textToAudio(text, sessionId) {
    const formData = new FormData();
    formData.append("text",       text);
    formData.append("session_id", sessionId);
    return apiFetch("POST", "/text-to-audio", formData, true);
}

// ---------------------------------------------------------------------------
// Report
// ---------------------------------------------------------------------------
async function generateReport(sessionId) {
    return apiFetch("POST", `/report/generate?session_id=${sessionId}`);
}

async function getReport(sessionId) {
    return apiFetch("GET", `/report/${sessionId}`);
}