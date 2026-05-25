// scripts/interview.js

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let sessionId      = null;
let questionIndex  = null;
let totalQuestions = 5;
let isRecording    = false;
let mediaRecorder  = null;
let audioChunks    = [];
let audioBlob      = null;
let audioObjectUrl = null;
let audioPlaying   = false;

// ---------------------------------------------------------------------------
// sessionStorage helpers
// ---------------------------------------------------------------------------
function saveQuestionIndex(index) {
    questionIndex = index;
    sessionStorage.setItem("question_index", String(index));
    console.log(`[Interview] questionIndex saved → ${index}`);
}

function loadQuestionIndex() {
    const stored  = sessionStorage.getItem("question_index");
    questionIndex = stored !== null ? parseInt(stored, 10) : null;
    return questionIndex;
}

// ---------------------------------------------------------------------------
// Issue 5 — Init: only ONE call to startInterview, no duplicate
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {

    // -- Read session_id from URL first, then sessionStorage
    const params  = new URLSearchParams(window.location.search);
    sessionId     = params.get("session_id")
                 || sessionStorage.getItem("session_id");

    const name    = sessionStorage.getItem("candidate_name") || "Candidate";
    totalQuestions= parseInt(
        sessionStorage.getItem("total_questions") || "5", 10
    );

    // Update UI
    const nameEl = document.getElementById("candidate-name");
    if (nameEl) nameEl.textContent = name;

    if (!sessionId) {
        showError(
            "No session found. "
            + '<a href="/" style="color:inherit;text-decoration:underline">'
            + "Please register first.</a>"
        );
        return;
    }

    // Persist session_id so it survives navigation
    sessionStorage.setItem("session_id", sessionId);

    console.log(`[Interview] Init | session=${sessionId}`);

    // Issue 5 — Only call startInterview ONCE unconditionally.
    // The original code had a branch that called it twice in some cases.
    await startInterview();
});

// ---------------------------------------------------------------------------
// Start interview
// ---------------------------------------------------------------------------
async function startInterview() {
    showState("loading");

    // Clear any stale question index before starting fresh
    sessionStorage.removeItem("question_index");
    questionIndex = null;

    try {
        console.log("[Interview] Calling agentRespond (first call)");

        // First call: BOTH must be null — no answer, no index
        const data = await agentRespond(sessionId, null, null);

        console.log("[Interview] First response:", data);
        handleAgentResponse(data);

    } catch (err) {
        console.error("[Interview] startInterview error:", err);
        showError(err.message);
    }
}

function retryInterview() {
    sessionStorage.removeItem("question_index");
    questionIndex = null;
    startInterview();
}

// ---------------------------------------------------------------------------
// Handle agent response
// ---------------------------------------------------------------------------
function handleAgentResponse(data) {
    console.log("[Interview] handleAgentResponse:", data);

    if (!data) {
        showError("Empty response from server.");
        return;
    }

    if (data.is_complete) {
        console.log("[Interview] Interview complete — redirecting to report");
        if (data.report) {
            sessionStorage.setItem("report", JSON.stringify(data.report));
        }
        sessionStorage.removeItem("question_index");
        window.location.href = `/report?session_id=${sessionId}`;
        return;
    }

    if (!data.question_text) {
        showError("No question received from server. Please try again.");
        return;
    }

    // Persist question index
    if (data.question_index !== null && data.question_index !== undefined) {
        saveQuestionIndex(data.question_index);
    }

    updateProgress(data.question_index, totalQuestions);
    setQuestion(data.question_text, data.question_index, totalQuestions);
    showState("interview");
    setRecordingUI("idle");

    // Fetch TTS — non-blocking, failure is silent
    fetchQuestionAudio(data.question_text);
}

// ---------------------------------------------------------------------------
// Progress
// ---------------------------------------------------------------------------
function updateProgress(current, total) {
    const pct = Math.min(100, Math.round(((current - 1) / total) * 100));
    const pctEl  = document.getElementById("progress-pct");
    const fillEl = document.getElementById("progress-fill");
    const dotsEl = document.getElementById("progress-dots");

    if (pctEl)  pctEl.textContent  = `${pct}% complete`;
    if (fillEl) fillEl.style.width = `${pct}%`;

    if (dotsEl) {
        dotsEl.innerHTML = "";
        for (let i = 0; i < total; i++) {
            const dot     = document.createElement("div");
            dot.className = "progress-dot";
            if (i < current - 1)       dot.classList.add("done");
            else if (i === current - 1) dot.classList.add("current");
            dotsEl.appendChild(dot);
        }
    }
}

// ---------------------------------------------------------------------------
// Question display
// ---------------------------------------------------------------------------
function setQuestion(text, index, total) {
    const badge    = document.getElementById("question-badge");
    const questionEl = document.getElementById("question-text");
    const audioBtn = document.getElementById("play-audio-btn");

    if (badge)      badge.textContent      = `Question ${index} of ${total}`;
    if (questionEl) questionEl.textContent = text || "Loading…";
    if (audioBtn) {
    audioBtn.style.display = "inline-flex";
    audioBtn.disabled = true;
    audioBtn.classList.remove("playing");
}
    const audioLabel = document.getElementById("audio-btn-text");
    if (audioLabel) audioLabel.textContent = "Play Audio";
    audioPlaying = false;
}

// ---------------------------------------------------------------------------
// TTS
// ---------------------------------------------------------------------------

async function fetchQuestionAudio(text) {
    const btn = document.getElementById("play-audio-btn");
    const audioEl = document.getElementById("question-audio");

    try {
        if (!btn || !audioEl) {
            console.error("[Interview] Audio elements missing");
            return;
        }

        // ALWAYS KEEP BUTTON VISIBLE
        btn.style.display = "inline-flex";
        btn.disabled = true;

        // RESET AUDIO
        audioPlaying = false;

        audioEl.pause();
        audioEl.currentTime = 0;
        audioEl.removeAttribute("src");
        audioEl.load();

        console.log("[Interview] Requesting TTS...");

        const data = await textToAudio(text, sessionId);

        console.log("[Interview] TTS response:", data);

        // VALIDATE RESPONSE
        if (!data || !data.audio_url) {
            console.error("[Interview] Invalid audio response:", data);

            const label = document.getElementById("audio-btn-text");
            if (label) {
                label.textContent = "Audio Unavailable";
            }

            return;
        }

        // FORCE FRESH URL
        const audioUrl =
            `${API_BASE}${data.audio_url}?t=${Date.now()}`;

        console.log("[Interview] Audio URL:", audioUrl);

        audioEl.src = audioUrl;
        audioEl.load();

        // ENABLE BUTTON
        btn.disabled = false;

        const label = document.getElementById("audio-btn-text");
        if (label) {
            label.textContent = "Play Audio";
        }

        audioEl.onended = () => {
            audioPlaying = false;

            btn.classList.remove("playing");

            const label = document.getElementById("audio-btn-text");
            if (label) {
                label.textContent = "Play Audio";
            }
        };

    } catch (err) {
        console.error("[Interview] TTS failed:", err);

        if (btn) {
            btn.style.display = "inline-flex";
            btn.disabled = true;
        }

        const label = document.getElementById("audio-btn-text");
        if (label) {
            label.textContent = "Audio Error";
        }
    }
}

function toggleAudio() {
    const audioEl = document.getElementById("question-audio");
    const btn     = document.getElementById("play-audio-btn");
    const label   = document.getElementById("audio-btn-text");
    if (!audioEl) return;

    if (audioPlaying) {
        audioEl.pause();
        audioPlaying = false;
        if (btn)   btn.classList.remove("playing");
        if (label) label.textContent = "Play Audio";
    } else {
        audioEl.play();
        audioPlaying = true;
        if (btn)   btn.classList.add("playing");
        if (label) label.textContent = "Playing…";
    }
}

// ---------------------------------------------------------------------------
// Recording
// ---------------------------------------------------------------------------
async function startRecording() {
    clearRecordingState();

    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount:     1,
                sampleRate:       16000,
                echoCancellation: true,
                noiseSuppression: true,
            },
        });

        const mimeType = [
            "audio/webm;codecs=opus",
            "audio/webm",
            "audio/ogg;codecs=opus",
            "audio/mp4",
        ].find(t => MediaRecorder.isTypeSupported(t)) || "";

        mediaRecorder = new MediaRecorder(stream, { mimeType });
        audioChunks   = [];

        mediaRecorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = () => {
            audioBlob      = new Blob(audioChunks, { type: mimeType || "audio/webm" });
            audioObjectUrl = URL.createObjectURL(audioBlob);
            const preview  = document.getElementById("recorded-audio");
            if (preview) preview.src = audioObjectUrl;
            stream.getTracks().forEach(t => t.stop());
            setRecordingUI("stopped");
        };

        mediaRecorder.onerror = () => {
            showInterviewError("Recording error. Please try again.");
            setRecordingUI("idle");
        };

        mediaRecorder.start(250);
        isRecording = true;
        setRecordingUI("recording");

    } catch (err) {
        const msg = err.name === "NotAllowedError"
            ? "Microphone access denied. Please allow mic permissions."
            : `Recording failed: ${err.message}`;
        showInterviewError(msg);
    }
}

function stopRecording() {
    if (mediaRecorder && isRecording) {
        mediaRecorder.stop();
        isRecording = false;
    }
}

function clearRecording() {
    if (audioObjectUrl) URL.revokeObjectURL(audioObjectUrl);
    clearRecordingState();
    setRecordingUI("idle");
}

function clearRecordingState() {
    audioBlob      = null;
    audioObjectUrl = null;
    audioChunks    = [];
}

// ---------------------------------------------------------------------------
// Submit answer
// ---------------------------------------------------------------------------
async function submitAnswer() {
    if (!audioBlob) {
        showInterviewError("No recording found. Please record your answer first.");
        return;
    }

    const currentIndex = loadQuestionIndex();
    if (currentIndex === null) {
        showInterviewError("Session state lost. Please refresh.");
        return;
    }

    console.log(
        `[Interview] submitAnswer | session=${sessionId} | index=${currentIndex}`
    );

    showProcessing(true);
    hideTranscript();

    try {
        // Step 1 — STT
        const sttData    = await audioToText(audioBlob, sessionId);
        const answerText = sttData.transcript || "";

        console.log(
            `[Interview] STT done | chars=${answerText.length} | ` +
            `preview='${answerText.slice(0, 60)}'`
        );

        showTranscript(answerText || "(No speech detected)");
        clearRecording();

        // KEEP transcript visible with current question
        await new Promise(resolve => setTimeout(resolve, 2500));

        // Step 2 — Agent respond
        const data = await agentRespond(sessionId, answerText, currentIndex);

        console.log("[Interview] agentRespond:", data);

        hideTranscript(); // hide old transcript before next question

        showProcessing(false);
        handleAgentResponse(data);

    } catch (err) {
        console.error("[Interview] submitAnswer error:", err);
        showProcessing(false);
        showInterviewError(err.message);
    }
}

// ---------------------------------------------------------------------------
// UI helpers
// ---------------------------------------------------------------------------
function showState(state) {
    ["loading-state", "error-state", "interview-ui"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add("hidden");
    });

    const map = {
        loading:   "loading-state",
        error:     "error-state",
        interview: "interview-ui",
    };

    const target = document.getElementById(map[state]);
    if (target) target.classList.remove("hidden");
}

function showError(msg) {
    const el = document.getElementById("error-message");
    if (el) el.innerHTML = msg;
    showState("error");
}

function showInterviewError(msg) {
    let errEl = document.getElementById("inline-error");
    if (!errEl) {
        errEl           = document.createElement("div");
        errEl.id        = "inline-error";
        errEl.className = "alert alert-error";
        const card      = document.getElementById("recorder-card");
        if (card) card.prepend(errEl);
    }
    errEl.textContent = msg;
    errEl.classList.remove("hidden");
    setTimeout(() => errEl.classList.add("hidden"), 6000);
}

function setRecordingUI(state) {
    const ids = {
        record: "record-btn",
        stop:   "stop-btn",
        redo:   "redo-btn",
        submit: "submit-answer-btn",
    };

    Object.values(ids).forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add("hidden");
    });

    ["waveform", "idle-label", "ready-label", "audio-preview"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add("hidden");
    });

    const stopBtn = document.getElementById("stop-btn");
    if (stopBtn) stopBtn.classList.remove("recording-pulse");

    if (state === "idle") {
        document.getElementById("record-btn")?.classList.remove("hidden");
        document.getElementById("idle-label")?.classList.remove("hidden");
    }
    if (state === "recording") {
        document.getElementById("stop-btn")?.classList.remove("hidden");
        document.getElementById("stop-btn")?.classList.add("recording-pulse");
        document.getElementById("waveform")?.classList.remove("hidden");
    }
    if (state === "stopped") {
        document.getElementById("redo-btn")?.classList.remove("hidden");
        document.getElementById("submit-answer-btn")?.classList.remove("hidden");
        document.getElementById("ready-label")?.classList.remove("hidden");
        document.getElementById("audio-preview")?.classList.remove("hidden");
    }
}

function showProcessing(show) {
    document.getElementById("processing-card")
        ?.classList.toggle("hidden", !show);
    document.getElementById("recorder-card")
        ?.classList.toggle("hidden", show);
}

function showTranscript(text) {
    const card = document.getElementById("transcript-card");
    const el   = document.getElementById("transcript-text");
    if (el)   el.textContent = text;
    if (card) card.classList.remove("hidden");
}

function hideTranscript() {
    document.getElementById("transcript-card")?.classList.add("hidden");
}