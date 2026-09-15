from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from src.database import get_db
from src.models import Business
from typing import Optional
from datetime import datetime, timezone
import csv
import io
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/v1/export", tags=["Export"])

@router.get("/businesses")
def export_businesses(
    since: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1, le=1000),
    is_valid: bool = True,
    format: str = Query("json"),
    db: Session = Depends(get_db)
):
    query = db.query(Business)
    
    if is_valid is not None:
        query = query.filter(Business.is_valid == is_valid)
    if since:
        query = query.filter(Business.discovered_at >= since)
        
    query = query.order_by(Business.discovered_at.desc())
    
    # --- CSV Export Path ---
    if format.lower() == "csv":
        # Ignore pagination for CSV export, stream all matching records
        all_items = query.all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        headers = ["name", "address", "phone", "email", "website", "category", "officename", "district", "statename", "email_source_url", "email_enrichment_status", "email_enriched_at"]
        writer.writerow(headers)
        
        for biz in all_items:
            writer.writerow([
                biz.name,
                biz.address,
                biz.phone,
                biz.email,
                biz.website,
                biz.category,
                biz.officename,
                biz.district,
                biz.state,
                biz.email_source_url,
                biz.email_enrichment_status,
                biz.email_enriched_at.isoformat() if biz.email_enriched_at else None
            ])
            
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]), 
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=businesses_export.csv"}
        )

    # --- JSON Export Path (Backward Compatible) ---
    total = query.count()
    items_db = query.offset((page - 1) * page_size).limit(page_size).all()
    total_pages = (total + page_size - 1) // page_size
    
    # Format according to API_CONTRACT.md
    items = []
    for biz in items_db:
        items.append({
            "name": biz.name,
            "address": biz.address,
            "phone": biz.phone,
            "email": biz.email,
            "website": biz.website,
            "category": biz.category,
            "officename": biz.officename,
            "district": biz.district,
            "statename": biz.state,
        })
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
        "export_metadata": {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "filter_since": since.isoformat() if since else None,
            "valid_only": is_valid
        }
    }
