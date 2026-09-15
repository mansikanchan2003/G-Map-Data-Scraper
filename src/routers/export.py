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
    is_valid: Optional[bool] = None,
    format: str = Query("csv", pattern="^(csv|json|excel)$"),
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
        all_items = query.all()
        
        output = io.StringIO()
        # Add UTF-8 BOM so Excel opens it correctly with Unicode
        output.write('\ufeff')
        writer = csv.writer(output)
        
        headers = ["name", "address", "phone", "email", "website", "category", "district", "state", "verified"]
        writer.writerow(headers)
        
        for biz in all_items:
            writer.writerow([
                biz.name,
                biz.address,
                biz.phone,
                biz.email,
                biz.website,
                biz.category,
                biz.district,
                biz.state,
                biz.is_valid
            ])
            
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]), 
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=businesses_export.csv"}
        )

    # --- Excel (XLSX) Export Path ---
    if format.lower() == "excel":
        import openpyxl
        from openpyxl.utils import get_column_letter
        from tempfile import NamedTemporaryFile
        
        all_items = query.all()
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Businesses"
        
        headers = ["name", "address", "phone", "email", "website", "category", "district", "state", "verified"]
        ws.append(headers)
        
        for biz in all_items:
            row = [
                biz.name,
                biz.address,
                biz.phone, # Openpyxl handles strings correctly without '="value"' hack if we specify cell type
                biz.email,
                biz.website,
                biz.category,
                biz.district,
                biz.state,
                biz.is_valid
            ]
            ws.append(row)
            
            # Explicitly set phone column as string data type
            phone_cell = ws.cell(row=ws.max_row, column=3)
            phone_cell.data_type = 's'
        
        # Auto-fit columns with a sensible maximum
        for col in ws.columns:
            max_length = 0
            column = [cell for cell in col]
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min((max_length + 2), 50) # Cap width at 50
            ws.column_dimensions[get_column_letter(column[0].column)].width = adjusted_width
            
        # Freeze header and apply auto-filter
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        
        with NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            wb.save(tmp.name)
            tmp_path = tmp.name
            
        import os
        with open(tmp_path, "rb") as f:
            file_data = f.read()
        os.remove(tmp_path)
        
        return StreamingResponse(
            iter([file_data]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=businesses_export.xlsx"}
        )

    # --- JSON Export Path (Backward Compatible) ---
    total = query.count()
    items_db = query.offset((page - 1) * page_size).limit(page_size).all()
    total_pages = (total + page_size - 1) // page_size if page_size else 1
    
    items = []
    for biz in items_db:
        items.append({
            "name": biz.name,
            "address": biz.address,
            "phone": biz.phone,
            "email": biz.email,
            "website": biz.website,
            "category": biz.category,
            "district": biz.district,
            "state": biz.state,
            "verified": biz.is_valid,
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
