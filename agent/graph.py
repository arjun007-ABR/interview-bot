# agent/graph.py

import logging
import sys
import os
from typing import Optional
from pathlib import Path

# ---------------------------------------------------------------------------
# Fix sys.path so nodes/ and agent/ are always importable
# regardless of where Python is invoked from.
#
# Adds the parent of this file's directory to sys.path.
#
# If structure is:
#   interview bot/
#   ├── agent/graph.py      ← this file
#   ├── nodes/
#   ├── models/
#   ├── services/
#   └── app.py
#
# Then Path(__file__).resolve().parent.parent = "interview bot/"
# which makes `import nodes.xxx` work correctly.
# ---------------------------------------------------------------------------
_THIS_FILE   = Path(__file__).resolve()          # .../interview bot/agent/graph.py
_AGENT_DIR   = _THIS_FILE.parent                 # .../interview bot/agent/
_PROJECT_DIR = _AGENT_DIR.parent                 # .../interview bot/

if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

# Also add agent/ itself for intra-agent imports
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

# ---------------------------------------------------------------------------
# Now imports will work correctly
# ---------------------------------------------------------------------------
from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from agent.state import InterviewState
from nodes.load_candidate    import load_candidate_node
from nodes.generate_question import generate_question_node
from nodes.evaluvate_answer   import evaluate_answer_node
from nodes.check_completion  import check_completion_node
from nodes.generate_report   import generate_report_node

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node wrappers — error guard
# ---------------------------------------------------------------------------
async def safe_load_candidate(state: InterviewState) -> InterviewState:
    if state.get("error"):
        return state
    return await load_candidate_node(state)


async def safe_generate_question(state: InterviewState) -> InterviewState:
    if state.get("error"):
        return state
    return await generate_question_node(state)


async def safe_evaluate_answer(state: InterviewState) -> InterviewState:
    if state.get("error"):
        return state
    return await evaluate_answer_node(state)


async def safe_check_completion(state: InterviewState) -> InterviewState:
    if state.get("error"):
        return state
    return await check_completion_node(state)


async def safe_generate_report(state: InterviewState) -> InterviewState:
    if state.get("error"):
        return state
    return await generate_report_node(state)


# ---------------------------------------------------------------------------
# Router — entry point
# ---------------------------------------------------------------------------
def route_entry(state: InterviewState):

    answer_text = state.get("answer_text")
    question_index = state.get("question_index")

    # --------------------------------------------------------------
    # FIRST REQUEST
    # No answer + no question index yet
    # --------------------------------------------------------------
    if not question_index and not answer_text:

        logger.info(
            f"[GRAPH] route_entry → load_candidate | "
            f"session={state['session_id']}"
        )

        return "load_candidate"

    # --------------------------------------------------------------
    # Candidate answered previous question
    # --------------------------------------------------------------
    logger.info(
        f"[GRAPH] route_entry → evaluate_answer | "
        f"session={state['session_id']} | "
        f"q_index={question_index}"
    )

    return "evaluate_answer"


# ---------------------------------------------------------------------------
# Router — after check_completion
# ---------------------------------------------------------------------------
def route_after_check(state: InterviewState) -> str:
    if state.get("error"):
        logger.error(
            f"[GRAPH] Error in state — routing to generate_report | "
            f"error={state['error']}"
        )
        return "generate_report"

    if state.get("is_complete"):
        logger.info(
            f"[GRAPH] Interview complete → generate_report | "
            f"session={state['session_id']}"
        )
        return "generate_report"

    logger.info(
        f"[GRAPH] Continuing → generate_question | "
        f"session={state['session_id']} | "
        f"next_index={state.get('question_index')}"
    )
    return "generate_question"


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------
def build_interview_graph():
    """
    FLOW:
    First call  (answer_text=None):
        START → load_candidate → generate_question → END

    Subsequent  (answer_text=str):
        START → evaluate_answer → check_completion
                    ├── not complete → generate_question → END
                    └── complete    → generate_report   → END
    """
    graph = StateGraph(InterviewState)

    # Register nodes
    graph.add_node("load_candidate",    safe_load_candidate)
    graph.add_node("generate_question", safe_generate_question)
    graph.add_node("evaluate_answer",   safe_evaluate_answer)
    graph.add_node("check_completion",  safe_check_completion)
    graph.add_node("generate_report",   safe_generate_report)

    # Entry routing
    graph.set_conditional_entry_point(
        route_entry,
        {
            "load_candidate":  "load_candidate",
            "evaluate_answer": "evaluate_answer",
        },
    )

    # First call path
    graph.add_edge("load_candidate",    "generate_question")
    graph.add_edge("generate_question", END)

    # Subsequent call path
    graph.add_edge("evaluate_answer", "check_completion")
    graph.add_conditional_edges(
        "check_completion",
        route_after_check,
        {
            "generate_question": "generate_question",
            "generate_report":   "generate_report",
        },
    )
    graph.add_edge("generate_report", END)

    compiled = graph.compile()
    logger.info("[GRAPH] Workflow compiled successfully.")
    return compiled


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_compiled_graph = None


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        try:
            _compiled_graph = build_interview_graph()
        except Exception as e:
            logger.error(f"[GRAPH] Compilation failed: {e}")
            raise RuntimeError(f"LangGraph compilation failed: {e}") from e
    return _compiled_graph


def reset_compiled_graph():
    global _compiled_graph
    _compiled_graph = None

# ---------------------------------------------------------------------------
# run_interview_graph
# ---------------------------------------------------------------------------
from sqlalchemy import select
from models.qa import QuestionAnswer


async def run_interview_graph(
    session_id: str,
    answer_text: Optional[str],
    question_index: Optional[int],
    db: AsyncSession,
) -> dict:

    graph = get_compiled_graph()

    is_first_call = answer_text is None

    logger.info(
        f"[GRAPH] run_interview_graph | "
        f"session={session_id} | "
        f"first_call={is_first_call} | "
        f"question_index={question_index} | "
        f"answer='{str(answer_text)[:40] if answer_text is not None else None}'"
    )

    # -----------------------------------------------------------------------
    # Load current question from DB
    # Needed while evaluating candidate answer
    # -----------------------------------------------------------------------
    current_question = None

    if question_index is not None:

        result = await db.execute(
            select(QuestionAnswer).where(
                QuestionAnswer.session_id == session_id,
                QuestionAnswer.question_index == question_index,
            )
        )

        qa = result.scalars().first()

        if qa:
            current_question = qa.question_text

            logger.info(
                f"[GRAPH] Loaded question from DB | "
                f"session={session_id} | "
                f"q_index={question_index}"
            )

        else:
            logger.warning(
                f"[GRAPH] Question not found in DB | "
                f"session={session_id} | "
                f"q_index={question_index}"
            )

    # -----------------------------------------------------------------------
    # Initial graph state
    # -----------------------------------------------------------------------
    initial_state: InterviewState = {

        "session_id":              session_id,

        "candidate_id":            None,
        "candidate_name":          None,
        "candidate_role":          None,
        "candidate_skills":        None,
        "candidate_experience":    None,
        "candidate_qualification": None,

        "question_index":          question_index,
        "total_questions":         None,

        # IMPORTANT FIX
        "current_question":        current_question,

        "previous_questions":      [],

        # SAFE FIX
        "answer_text":             (answer_text or "").strip(),

        "score":                   None,
        "feedback":                None,
        "is_complete":             False,
        "report":                  None,
        "error":                   None,

        "db":                      db,
    }

    # -----------------------------------------------------------------------
    # Execute graph
    # -----------------------------------------------------------------------
    final_state = await graph.ainvoke(initial_state)

    # -----------------------------------------------------------------------
    # Handle graph errors
    # -----------------------------------------------------------------------
    if final_state.get("error"):

        logger.error(
            f"[GRAPH] Error in state | "
            f"session={session_id} | "
            f"error={final_state['error']}"
        )

        raise RuntimeError(final_state["error"])

    # -----------------------------------------------------------------------
    # Final API response
    # -----------------------------------------------------------------------
    result = {
        "question_text":  final_state.get("current_question"),
        "question_index": final_state.get("question_index"),
        "is_complete":    final_state.get("is_complete", False),
        "report":         final_state.get("report"),
    }

    logger.info(
        f"[GRAPH] Done | "
        f"session={session_id} | "
        f"q_index={result['question_index']} | "
        f"is_complete={result['is_complete']} | "
        f"has_question={result['question_text'] is not None}"
    )

    return result


# ---------------------------------------------------------------------------
# run_report_graph
# ---------------------------------------------------------------------------
async def run_report_graph(
    session_id: str,
    db        : AsyncSession,
) -> dict:
    from models.session   import InterviewSession
    from models.candidate import Candidate

    session_result = await db.execute(
        select(InterviewSession).where(
            InterviewSession.session_id == session_id
        )
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    candidate_result = await db.execute(
        select(Candidate).where(Candidate.id == session.candidate_id)
    )
    candidate = candidate_result.scalar_one_or_none()
    if not candidate:
        raise ValueError(f"Candidate not found: {session_id}")

    state: InterviewState = {
        "session_id":              session_id,
        "candidate_id":            candidate.id,
        "candidate_name":          candidate.name,
        "candidate_role":          candidate.role,
        "candidate_skills":        candidate.skills,
        "candidate_experience":    candidate.experience,
        "candidate_qualification": candidate.qualification,
        "question_index":          session.current_question,
        "total_questions":         session.total_questions,
        "current_question":        None,
        "previous_questions":      [],
        "answer_text":             None,
        "score":                   None,
        "feedback":                None,
        "is_complete":             True,
        "report":                  None,
        "error":                   None,
        "db":                      db,
    }

    logger.info(f"[GRAPH] run_report_graph | session={session_id}")
    final_state = await safe_generate_report(state)

    if final_state.get("error"):
        raise RuntimeError(final_state["error"])

    return final_state.get("report", {})


# ---------------------------------------------------------------------------
# Run directly: python agent/graph.py → saves graph PNG
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    graph = get_compiled_graph()
    try:
        png_data = graph.get_graph().draw_mermaid_png()
        with open("interview_graph.png", "wb") as f:
            f.write(png_data)
        print("Saved → interview_graph.png")
    except Exception as e:
        print(f"PNG failed ({e}). Mermaid source:\n")
        print(graph.get_graph().draw_mermaid())