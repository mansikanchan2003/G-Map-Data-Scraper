from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from src.database import get_db
from src.models import Business
from typing import Optional
from datetime import datetime, timezone
import csv
import io
import os
from fastapi.responses import StreamingResponse, FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel
from typing import List, Optional
from fastapi import HTTPException
from src.services.google_sheets import GoogleSheetsService

class GoogleSheetsExportRequest(BaseModel):
    filters: dict = {}
    selected_ids: List[str] = []
    export_all: bool = False

router = APIRouter(prefix="/api/v1/export", tags=["Export"])

@router.post("/google-sheets")
def export_google_sheets(
    request: GoogleSheetsExportRequest,
    db: Session = Depends(get_db)
):
    try:
        service = GoogleSheetsService()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets service error: {str(e)}")

    query = db.query(Business)

    if not request.export_all:
        if request.selected_ids:
            query = query.filter(Business.business_id.in_(request.selected_ids))
        else:
            filters = request.filters
            if filters.get("is_valid") is not None:
                query = query.filter(Business.is_valid == filters["is_valid"])
            if filters.get("since"):
                from dateutil.parser import parse
                try:
                    since_dt = parse(filters["since"])
                    query = query.filter(Business.discovered_at >= since_dt)
                except Exception:
                    pass
            if filters.get("category") and filters.get("category") != "All":
                query = query.filter(Business.category == filters["category"])
            if filters.get("state") and filters.get("state") != "All":
                query = query.filter(Business.state == filters["state"])
            if filters.get("district") and filters.get("district") != "All":
                query = query.filter(Business.district == filters["district"])
            if filters.get("search"):
                search = f"%{filters['search']}%"
                query = query.filter(
                    (Business.name.ilike(search)) |
                    (Business.phone.ilike(search)) |
                    (Business.address.ilike(search))
                )

    query = query.order_by(Business.discovered_at.desc())
    query = query.execution_options(stream_results=True)

    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        sheet = service.create_export_sheet(f"G-Map Scraper Export - {timestamp}")
        worksheet = sheet.sheet1

        service.write_headers(worksheet)
        rows_exported = service.stream_rows_to_sheet(worksheet, query.yield_per(1000))

        return {
            "status": "success",
            "spreadsheet_id": sheet.id,
            "spreadsheet_url": sheet.url,
            "rows_exported": rows_exported
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google Sheets Export Failed: {str(e)}")

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
    query = query.execution_options(stream_results=True)
    
    # --- CSV Export Path ---
    if format.lower() == "csv":
        def iter_csv():
            output = io.StringIO()
            # Add UTF-8 BOM so Excel opens it correctly with Unicode
            output.write('\ufeff')
            writer = csv.writer(output)
            
            headers = ["name", "address", "phone", "email", "website", "category", "district", "state", "verified"]
            writer.writerow(headers)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

            for biz in query.yield_per(1000):
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
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

        return StreamingResponse(
            iter_csv(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=businesses_export.csv"}
        )

    # --- Excel (XLSX) Export Path ---
    if format.lower() == "excel":
        import openpyxl
        from openpyxl.cell import WriteOnlyCell
        from tempfile import NamedTemporaryFile
        
        wb = openpyxl.Workbook(write_only=True)
        ws = wb.create_sheet("Businesses")
        
        headers = ["name", "address", "phone", "email", "website", "category", "district", "state", "verified"]
        ws.append(headers)
        
        for biz in query.yield_per(1000):
            row_data = [
                biz.name,
                biz.address,
                biz.phone,
                biz.email,
                biz.website,
                biz.category,
                biz.district,
                biz.state,
                biz.is_valid
            ]
            
            # Format phone number as string explicitly
            cells = []
            for idx, val in enumerate(row_data):
                cell = WriteOnlyCell(ws, value=val)
                if idx == 2: # phone column (0-indexed)
                    cell.data_type = 's'
                cells.append(cell)

            ws.append(cells)
        
        with NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            wb.save(tmp.name)
            tmp_path = tmp.name
            
        return FileResponse(
            path=tmp_path,
            filename="businesses_export.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            background=BackgroundTask(os.remove, tmp_path)
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
