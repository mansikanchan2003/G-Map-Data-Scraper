from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, func

from src.database import Base


class StudioImagePrompt(Base):
    """
    One image the Studio asked for: the prompt, how it was judged, and what
    became of it.

    Kept so later images are made from what worked. The check judges each
    photo as it is made (a sign that read back right, no stray lettering, a
    real-looking photo); the reviewer judges it after — keeping it by
    approving the draft, or asking for another with "New photo". The rows
    outlive their draft, so what was learned is not lost when one is deleted.
    """
    __tablename__ = "studio_image_prompts"

    prompt_id = Column(String(32), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    template_id = Column(String(32), ForeignKey("whatsapp_templates.template_id", ondelete="SET NULL"),
                         nullable=True, index=True)
    # sign: the phrase printed on a sign in the photo; plain: no text at all.
    kind = Column(String(10), nullable=False)
    # Which wording wrapped the scene (image_prompts.STYLES).
    style = Column(String(20), nullable=False)
    language_code = Column(String(10), nullable=True)
    target_state = Column(String(100), nullable=True)
    scene = Column(Text, nullable=True)
    phrase = Column(String(200), nullable=True)
    prompt = Column(Text, nullable=False)
    model = Column(String(100), nullable=True)
    seed = Column(Integer, nullable=True)
    media_id = Column(String(64), nullable=True)
    check = Column(JSON, nullable=True)
    # False when the vision model's answer could not be read: not judged.
    checked = Column(Boolean, nullable=False, default=True)
    passed = Column(Boolean, nullable=False, default=False)
    # A misspelt sign, or lettering where there should be none.
    gibberish = Column(Boolean, nullable=False, default=False)
    # unused | in_review | kept | replaced | draft_rejected
    outcome = Column(String(20), nullable=False, default="unused")
    # Why it failed, in a few words, for the agent to read next time.
    note = Column(String(300), nullable=True)
