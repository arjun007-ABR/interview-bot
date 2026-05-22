// scripts/report.js

document.addEventListener("DOMContentLoaded", async () => {
    const params    = new URLSearchParams(window.location.search);
    const sessionId = params.get("session_id")
                   || sessionStorage.getItem("session_id");
    const name      = sessionStorage.getItem("candidate_name") || "Candidate";

    const nameEl = document.getElementById("report-candidate-name");
    if (nameEl) nameEl.textContent = name;

    if (!sessionId) {
        showError("No session found.");
        return;
    }

    await loadReport(sessionId);
});

async function loadReport(sessionId) {
    showState("loading");

    try {
        // Try sessionStorage cache first (passed from interview page)
        const cached = sessionStorage.getItem("report");
        if (cached) {
            console.log("[Report] Loading from sessionStorage cache");
            renderReport(JSON.parse(cached));
            return;
        }

        console.log("[Report] Fetching from API");
        const data = await getReport(sessionId);
        renderReport(data);

    } catch (err) {
        console.error("[Report] Load error:", err);
        showError(err.message);
    }
}

function renderReport(report) {
    if (!report) {
        showError("Report data is empty.");
        return;
    }

    document.getElementById("overall-score").textContent =
        (report.overall_score || 0).toFixed(1);

    renderHireBadge(report.hire_recommendation);

    document.getElementById("strengths-text").textContent =
        report.strengths  || "Not available.";
    document.getElementById("weaknesses-text").textContent =
        report.weaknesses || "Not available.";

    renderQAList(report.questions_answers || []);
    showState("report");
}

function renderHireBadge(recommendation) {
    const badgeEl = document.getElementById("hire-badge");
    if (!badgeEl) return;

    const map = {
        "HIRE":    { cls: "hire",    icon: "✓", label: "HIRE" },
        "MAYBE":   { cls: "maybe",   icon: "◐", label: "MAYBE" },
        "NO HIRE": { cls: "no-hire", icon: "✗", label: "NO HIRE" },
    };

    const config      = map[recommendation] || map["NO HIRE"];
    badgeEl.className = `hire-badge ${config.cls}`;
    badgeEl.innerHTML = `<span>${config.icon}</span> ${config.label}`;
}

function renderQAList(qaList) {
    const container = document.getElementById("qa-list");
    if (!container) return;

    container.innerHTML = "";

    if (!qaList.length) {
        container.innerHTML =
            "<p style='color:var(--slate-400);font-size:.875rem'>" +
            "No Q&A records found.</p>";
        return;
    }

    qaList.forEach((qa) => {
        const item       = document.createElement("div");
        item.className   = "qa-item";
        item.innerHTML   = `
            <div class="qa-header">
                <p class="qa-question">
                    Q${qa.question_index}: ${escapeHtml(qa.question_text || "")}
                </p>
                <span class="score-pill ${getScoreClass(qa.score)}">
                    ${(qa.score || 0).toFixed(1)}/10
                </span>
            </div>
            <p class="qa-answer">
                <span>Answer: </span>
                ${escapeHtml(qa.answer_text || "No answer provided")}
            </p>
            <p class="qa-feedback">${escapeHtml(qa.feedback || "")}</p>
        `;
        container.appendChild(item);
    });
}

function getScoreClass(score) {
    if (score >= 8) return "score-excellent";
    if (score >= 6) return "score-good";
    if (score >= 4) return "score-average";
    return "score-poor";
}

function escapeHtml(str) {
    const div       = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

function showState(state) {
    ["loading-state", "error-state", "report-content"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add("hidden");
    });

    const map = {
        loading: "loading-state",
        error:   "error-state",
        report:  "report-content",
    };

    const target = document.getElementById(map[state]);
    if (target) target.classList.remove("hidden");
}

function showError(msg) {
    const el = document.getElementById("error-message");
    if (el) el.textContent = msg;
    showState("error");
}

function newInterview() {
    sessionStorage.clear();
    window.location.href = "/";
}