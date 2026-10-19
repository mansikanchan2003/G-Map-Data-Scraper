"""
Teaching the bot: a question it left for a person, tied to the answer that covers it.

When a question reaches the team because the bot did not recognise it, and
one of Eko's confirmed answers does cover it, "Teach the bot" in the inbox
records the question against that answer. The bot then answers a later
question that says nearly the same thing itself (eko_knowledge._taught), in
the person's language. The answers stay Eko's; only how people ask grows.

Kept in app_settings under faq_learning as {faq_id: [question, ...]}.
"""
import json
from typing import Dict, List

from sqlalchemy.orm import Session

from src.models.app_setting import AppSetting
from src.services import eko_knowledge

KEY = "faq_learning"
MAX_PER_ANSWER = 200


def _row(db: Session) -> AppSetting:
    row = db.query(AppSetting).filter(AppSetting.key == KEY).first()
    if row is None:
        row = AppSetting(key=KEY, value=None)
        db.add(row)
    return row


def taught(db: Session) -> Dict[str, List[str]]:
    row = db.query(AppSetting).filter(AppSetting.key == KEY).first()
    try:
        data = json.loads(row.value) if row and row.value else {}
    except ValueError:
        data = {}
    return {k: list(v) for k, v in data.items() if isinstance(v, list)}


def load(db: Session) -> None:
    """Hand what has been taught to the matcher."""
    eko_knowledge.LEARNED.clear()
    eko_knowledge.LEARNED.update(taught(db))


def teach(db: Session, faq_id: str, question: str) -> Dict[str, List[str]]:
    if faq_id not in eko_knowledge._BY_ID:
        raise ValueError("Unknown answer")
    question = " ".join((question or "").split())[:300]
    if not question:
        raise ValueError("The question is empty")
    data = taught(db)
    examples = [q for q in data.get(faq_id, []) if q.lower() != question.lower()]
    data[faq_id] = (examples + [question])[-MAX_PER_ANSWER:]
    _row(db).value = json.dumps(data, ensure_ascii=False)
    db.commit()
    load(db)
    return data


def forget(db: Session, faq_id: str, question: str) -> Dict[str, List[str]]:
    data = taught(db)
    data[faq_id] = [q for q in data.get(faq_id, []) if q != question]
    if not data[faq_id]:
        data.pop(faq_id)
    _row(db).value = json.dumps(data, ensure_ascii=False)
    db.commit()
    load(db)
    return data


def answers(db: Session) -> List[dict]:
    """Every answer the bot can give, with what it has been taught for each."""
    data = taught(db)
    return [{"id": f["id"], "question": f["question"], "source": f.get("source", "Creator Pack"),
             "answer": f["answer"].get("hinglish") or f["answer"]["en"], "taught": data.get(f["id"], [])}
            for f in eko_knowledge.FAQ]
