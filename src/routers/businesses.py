from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/businesses", tags=["Businesses"])

# Phase 2 implementations
@router.get("")
def list_businesses():
    return {"message": "Not implemented in Phase 1"}
