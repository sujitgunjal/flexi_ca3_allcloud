"""API for the persisted decision-evaluation report and runner."""

import json
from json import JSONDecodeError
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.decision.paths import REPORT_PATH

router = APIRouter()
_run_lock = Lock()


class EvaluationResultsResponse(BaseModel):
    available: bool
    report: dict[str, Any] | None


def _read_report(path: Path | None = None) -> dict[str, Any] | None:
    path = path or REPORT_PATH
    if not path.exists():
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Saved evaluation report is unreadable.") from exc
    if not isinstance(report, dict):
        raise HTTPException(status_code=500, detail="Saved evaluation report has an invalid format.")
    return report


def _run_evaluation() -> dict[str, Any]:
    from app.decision.evaluation.runner import evaluate

    return evaluate()


@router.get("/results", response_model=EvaluationResultsResponse)
def get_evaluation_results():
    report = _read_report()
    return EvaluationResultsResponse(available=report is not None, report=report)


@router.post("/run")
def run_evaluation():
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="An evaluation is already running.")
    try:
        try:
            report = _run_evaluation()
        except SystemExit as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc) or "Evaluation could not run with the available predictions.",
            ) from exc
        if not isinstance(report, dict):
            raise HTTPException(status_code=500, detail="Evaluation returned an invalid report.")
        return report
    finally:
        _run_lock.release()
