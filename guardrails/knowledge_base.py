"""Reference information for the assistant.

The application domain is a student-services help desk for a fictional
university, the Himalaya Institute of Technology (HIT). The assistant may only
answer from these documents, which is what the groundedness guardrail checks
against.
"""

from __future__ import annotations

import re

KNOWLEDGE_BASE: dict[str, dict[str, str]] = {
    "KB-001": {
        "title": "Library services",
        "text": (
            "The main library is open from 8:00 to 22:00 on weekdays and from 10:00 to 18:00 on weekends. "
            "Students can borrow up to 10 books for 21 days. "
            "Late returns are charged NPR 10 per book per day."
        ),
    },
    "KB-002": {
        "title": "Examination rules",
        "text": (
            "Students must arrive at the exam hall 15 minutes before the exam starts. "
            "Mobile phones are not allowed in the exam hall. "
            "A student who misses an exam because of illness must submit a medical certificate within 5 working days to apply for a make-up exam."
        ),
    },
    "KB-003": {
        "title": "Assignment submission",
        "text": (
            "Assignments must be submitted through the Moodle portal before 23:59 on the due date. "
            "Late submissions lose 10 percent of the marks per day and are not accepted after 5 days. "
            "Extensions can be requested from the module leader at least 48 hours before the deadline."
        ),
    },
    "KB-004": {
        "title": "Tuition fees",
        "text": (
            "Semester tuition fees must be paid by the 15th day of the semester. "
            "A late payment fee of NPR 500 applies after the deadline. "
            "Students can pay in two installments if they apply to the Finance Office."
        ),
    },
    "KB-005": {
        "title": "Scholarships",
        "text": (
            "Merit scholarships cover 50 percent of tuition for students with a GPA of 3.6 or higher. "
            "Need-based scholarship applications open in January each year."
        ),
    },
    "KB-006": {
        "title": "IT help desk",
        "text": (
            "Students can reset their portal password at the IT help desk in Block B or through the self-service reset page. "
            "The IT help desk is open from 9:00 to 17:00, Sunday to Friday. "
            "IT staff will never ask for your password by email."
        ),
    },
    "KB-007": {
        "title": "Student wellbeing",
        "text": (
            "The Student Wellbeing Centre offers free and confidential counselling. "
            "Counselling appointments can be booked at the front desk of Block C. "
            "In an emergency, students should call the campus emergency line on extension 100 or go to the nearest hospital."
        ),
    },
    "KB-008": {
        "title": "Contact directory",
        "text": (
            "The Registrar's Office can be contacted at registrar@hit.edu.np. "
            "The Finance Office can be contacted at finance@hit.edu.np."
        ),
    },
}

# Institutional contact details that are public and may appear in answers.
PUBLIC_CONTACTS = {"registrar@hit.edu.np", "finance@hit.edu.np"}

STOPWORDS = set(
    """a an the and or but if of to in on at by for from with without into onto is are was were be been being
    do does did can could should would will shall may might must i you he she it we they me my your our their his her
    its this that these those there here what which who whom whose when where why how all any some no not only
    just than then so as about up down out over under again more most such own same too very per each also
    please tell know want need get got have has had am""".split()
)


def tokenize(text: str) -> list[str]:
    """Lower-case content words with a crude plural/suffix strip."""
    words = re.findall(r"[a-z0-9]+(?:[:.][0-9]+)?", text.lower())
    out = []
    for w in words:
        if w in STOPWORDS:
            continue
        if len(w) > 5 and w.endswith("ing"):
            w = w[:-3]
        elif len(w) > 4 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 4 and w.endswith(("ed", "es")) and not w.endswith("ss"):
            w = w[:-2]
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text.strip())
    # Re-join pieces that were split after an abbreviation such as "Dr." or "e.g.".
    sentences: list[str] = []
    for part in parts:
        if sentences and re.search(r"\b(Dr|Mr|Mrs|Ms|Prof|St|e\.g|i\.e|etc|No)\.$", sentences[-1]):
            sentences[-1] += " " + part
        else:
            sentences.append(part)
    return [s.strip() for s in sentences if s.strip()]


def retrieve(query: str, k: int = 2) -> dict[str, str]:
    """Return the k most relevant documents by token overlap (a tiny stand-in for RAG)."""
    q = set(tokenize(query))
    scored = []
    for doc_id, doc in KNOWLEDGE_BASE.items():
        d = set(tokenize(doc["title"] + " " + doc["text"]))
        score = len(q & d)
        if score:
            scored.append((score, doc_id))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return {doc_id: KNOWLEDGE_BASE[doc_id]["text"] for _, doc_id in scored[:k]}
