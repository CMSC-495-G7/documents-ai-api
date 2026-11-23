"""Scoring for the Phase 4.6 evaluation set (evals/questions.json).

Plain functions on plain data, so they're easy to test. run_eval does the asking.
"""

import json
from pathlib import Path

from ask.services import NO_ANSWER

# PLAN.md 4.6 targets
TARGET_RETRIEVAL_HITS = 12  # of the 15 answerable questions
TARGET_NOT_FOUND = 4  # of the 5 unanswerable ones
TARGET_FAST_SHARE = 0.9  # 9 of 10 answers in under SLOW_SECONDS
SLOW_SECONDS = 30

KINDS = ("answerable", "unanswerable")


def load_questions(path):
    """The question set, checked so a typo fails before anything is asked."""
    questions = json.loads(Path(path).read_text(encoding="utf-8"))
    for question in questions:
        if question.get("kind") not in KINDS:
            raise ValueError(f"{question.get('id')}: kind must be one of {KINDS}")
        if question["kind"] == "answerable" and not (question.get("document") and question.get("pages")):
            raise ValueError(f"{question['id']}: answerable questions need a document and pages")
    return questions


def retrieval_hit(question, citations):
    """True when a citation comes from the expected document and one of its expected pages."""
    return any(
        citation["document_title"] == question["document"] and citation["page"] in question["pages"]
        for citation in citations
    )


def not_found(answer_text, used_llm):
    """True when the cutoff stopped it: the "not found" reply, without calling the LLM."""
    return answer_text == NO_ANSWER and not used_llm


def score(question, answer_text, used_llm, citations, seconds):
    """One row of the results."""
    row = {
        "id": question["id"],
        "kind": question["kind"],
        "question": question["question"],
        "answer": answer_text,
        "used_llm": used_llm,
        "citations": citations,
        "seconds": round(seconds, 2),
    }
    if question["kind"] == "answerable":
        row["expected"] = {"document": question["document"], "pages": question["pages"]}
        row["retrieval_hit"] = retrieval_hit(question, citations)
    else:
        row["not_found"] = not_found(answer_text, used_llm)
    return row


def summarize(rows):
    """Counts and whether each performance target was met."""
    answerable = [row for row in rows if row["kind"] == "answerable"]
    unanswerable = [row for row in rows if row["kind"] == "unanswerable"]
    hits = sum(row["retrieval_hit"] for row in answerable)
    not_found_count = sum(row["not_found"] for row in unanswerable)
    fast = sum(row["seconds"] < SLOW_SECONDS for row in rows)
    times = sorted(row["seconds"] for row in rows)

    return {
        "retrieval_hits": hits,
        "answerable": len(answerable),
        "not_found": not_found_count,
        "unanswerable": len(unanswerable),
        "fast": fast,
        "total": len(rows),
        "slowest_seconds": times[-1] if times else 0,
        "met": {
            "retrieval": hits >= TARGET_RETRIEVAL_HITS,
            "not_found": not_found_count >= TARGET_NOT_FOUND,
            "speed": bool(rows) and fast / len(rows) >= TARGET_FAST_SHARE,
        }
    }