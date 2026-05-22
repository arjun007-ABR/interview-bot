// scripts/register.js

document.addEventListener("DOMContentLoaded", () => {

    const form      = document.getElementById("register-form");
    const submitBtn = document.getElementById("submit-btn");
    const btnText   = document.getElementById("btn-text");
    const spinner   = document.getElementById("btn-spinner");
    const errBanner = document.getElementById("form-error");

    if (!form) {
        console.error("[Register] register-form element not found in DOM.");
        return;
    }

    // ------------------------------------------------------------------
    // Validation rules
    // ------------------------------------------------------------------
    const rules = {
        name:          { min: 2, label: "Full Name" },
        qualification: { min: 2, label: "Qualification" },
        experience:    { min: 1, label: "Experience" },
        skills:        { min: 1, label: "Skills" },
        role:          { min: 2, label: "Role" },
    };

    function validateForm(data) {
        const errors = {};
        for (const [field, rule] of Object.entries(rules)) {
            const val = (data[field] || "").trim();
            if (!val || val.length < rule.min) {
                errors[field] = `${rule.label} is required.`;
            }
        }
        return errors;
    }

    function showFieldErrors(errors) {
        document.querySelectorAll(".field-error")
            .forEach(el => el.textContent = "");
        document.querySelectorAll("input")
            .forEach(el => el.classList.remove("invalid"));

        for (const [field, msg] of Object.entries(errors)) {
            const errEl   = document.getElementById(`${field}-error`);
            const inputEl = document.getElementById(field);
            if (errEl)   errEl.textContent = msg;
            if (inputEl) inputEl.classList.add("invalid");
        }
    }

    function clearFieldErrors() {
        document.querySelectorAll(".field-error")
            .forEach(el => el.textContent = "");
        document.querySelectorAll("input")
            .forEach(el => el.classList.remove("invalid"));
    }

    function showError(msg) {
        errBanner.textContent = msg;
        errBanner.classList.remove("hidden");
    }

    function hideError() {
        errBanner.textContent = "";
        errBanner.classList.add("hidden");
    }

    function setLoading(loading) {
        submitBtn.disabled      = loading;
        btnText.textContent     = loading
            ? "Setting up your interview…"
            : "Start Interview";
        spinner.classList.toggle("hidden", !loading);
    }

    // Clear errors on input
    form.querySelectorAll("input").forEach(input => {
        input.addEventListener("input", () => {
            const errEl = document.getElementById(`${input.name}-error`);
            if (errEl) errEl.textContent = "";
            input.classList.remove("invalid");
            hideError();
        });
    });

    // ------------------------------------------------------------------
    // Submit
    // ------------------------------------------------------------------
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        clearFieldErrors();
        hideError();

        const data = {
            name:          document.getElementById("name").value.trim(),
            qualification: document.getElementById("qualification").value.trim(),
            experience:    document.getElementById("experience").value.trim(),
            skills:        document.getElementById("skills").value.trim(),
            role:          document.getElementById("role").value.trim(),
        };

        const errors = validateForm(data);
        if (Object.keys(errors).length > 0) {
            showFieldErrors(errors);
            return;
        }

        setLoading(true);

        try {
            const session = await createSession(data);

            console.log("[Register] Session created:", session);

            // Persist to sessionStorage
            sessionStorage.setItem("session_id",      session.session_id);
            sessionStorage.setItem("candidate_name",  data.name);
            sessionStorage.setItem("total_questions", String(session.total_questions));
            // Clear any stale question index from previous sessions
            sessionStorage.removeItem("question_index");

            // Issue 4 + 7 — Redirect using path (not .html extension)
            // Works whether served by FastAPI (/interview) or file system
            const redirectUrl = `/interview?session_id=${session.session_id}`;
            console.log("[Register] Redirecting to:", redirectUrl);
            window.location.href = redirectUrl;

        } catch (err) {
            console.error("[Register] Error:", err);
            showError(err.message || "Failed to create session. Please try again.");
            setLoading(false);
        }
    });

});