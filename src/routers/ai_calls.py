"""
The AI calling agent's webhook: Voxomos posts every finished call here.

Public (Voxomos carries no session cookie), so it is admitted only with the
shared secret in the X-Webhook-Secret header (VOXOMOS_WEBHOOK_SECRET). With
no secret set, every call is refused.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from src.database import get_db
from src.services import ai_calls

router = APIRouter(prefix="/api/v1/calls", tags=["AI calls"])


@router.post("/voxomos/webhook")
async def voxomos_webhook(request: Request, x_webhook_secret: str = Header(default=""),
                          db: Session = Depends(get_db)):
    if not ai_calls.secret_ok(x_webhook_secret):
        raise HTTPException(status_code=401, detail="Wrong or missing webhook secret")
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="The body is not JSON")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="The body must be one call, as a JSON object")
    try:
        call = ai_calls.receive(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "call_id": call.call_id, "outcome": call.outcome}
