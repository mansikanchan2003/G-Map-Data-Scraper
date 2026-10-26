"""
Every run of an AutoGMap agent, with its whole execution chain (the team's
"agentic platform" blueprint, 2026-10-26): the prompt, the context injected
into it, what the agent produced, and what a person finally kept. Written by
agent_telemetry.py; read by the Agent quality page.
"""
from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text, func

from src.database import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    run_id = Column(String(32), primary_key=True)
    # template_writer | business_agent | bot_faq | bot_reply_disposition | inbox_ready_reply
    agent = Column(String(40), nullable=False, index=True)
    # What the output belongs to: a template draft, or a chat (its phone).
    subject_type = Column(String(20), nullable=False)
    subject_id = Column(String(64), nullable=False, index=True)
    model = Column(String(120), nullable=True)
    # The input: the full prompt for a language model, the lead's message for the bot.
    prompt = Column(Text, nullable=True)
    # The context injected, chunk by chunk: [{source, ref, text, tokens, score}].
    context = Column(JSON, nullable=True)
    output = Column(Text, nullable=True)
    # The evaluator: what AutoGMap's own checks found, apart from the agent that wrote it:
    # {"checks": [{"name", "passed", "detail"}], "first_problems": [...], "repaired": bool}.
    evaluation = Column(JSON, nullable=True)
    # What a person finally kept (sent, submitted or recorded), when they did.
    final_output = Column(Text, nullable=True)
    # pending | accepted | edited | rejected | failed
    outcome = Column(String(20), nullable=False, default="pending", index=True)
    # Levenshtein distance between output and final_output, and the same over the longer length.
    edit_distance = Column(Integer, nullable=True)
    edit_ratio = Column(Float, nullable=True)
    # Estimated tokens (characters / 4) unless the model reported them.
    prompt_tokens = Column(Integer, nullable=True)
    context_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    error = Column(String(500), nullable=True)
    finalized_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    finalized_at = Column(DateTime(timezone=True), nullable=True)
