"""
Prosty FastAPI, udostępniający endpoint do alokacji.
Użycie lokalne (wymaga instalacji fastapi+uvicorn):
    pip install fastapi uvicorn
    uvicorn backend.api:app --reload
"""
from fastapi import FastAPI, UploadFile, File, Form
from typing import List
import io, csv

from .app import allocate_costs, _read_csv_any, REQUIRED_COA_COLS, REQUIRED_COST_COLS, REQUIRED_ALLOCATION_COLS

app = FastAPI(title="Controlling Allocation API")

def read_uploaded_csv(file: UploadFile, req_cols):
    content = file.file.read().decode("utf-8")
    return _read_csv_any(io.StringIO(content), req_cols)

@app.post("/allocate")
async def allocate(
    coa: UploadFile = File(...),
    costs: UploadFile = File(...),
    alloc: UploadFile | None = File(None),
):
    coa_rows = read_uploaded_csv(coa, REQUIRED_COA_COLS)
    costs_rows = read_uploaded_csv(costs, REQUIRED_COST_COLS)
    alloc_rows = read_uploaded_csv(alloc, REQUIRED_ALLOCATION_COLS) if alloc else []
    result, notes = allocate_costs(coa_rows, costs_rows, alloc_rows)
    return {"result": result, "notes": notes}
