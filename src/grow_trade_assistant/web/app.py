from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from grow_trade_assistant.config import Settings, load_settings
from grow_trade_assistant.pipeline import run_analysis

logger = logging.getLogger(__name__)

_analysis_lock = threading.Lock()
_analysis_running = False
_analysis_error: str | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="Grow Trade Assistant", version="0.2.0")
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    def _latest_report_path() -> Path | None:
        reports_dir = settings.reports_dir
        if not reports_dir.exists():
            return None
        files = sorted(reports_dir.glob("*.json"), reverse=True)
        return files[0] if files else None

    def _load_report(path: Path | None = None) -> dict[str, Any]:
        p = path or _latest_report_path()
        if not p or not p.exists():
            raise HTTPException(status_code=404, detail="No report found. Run analysis first.")
        return json.loads(p.read_text(encoding="utf-8"))

    @app.get("/", response_class=HTMLResponse)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        global _analysis_running, _analysis_error
        latest = _latest_report_path()
        return {
            "analysis_running": _analysis_running,
            "analysis_error": _analysis_error,
            "latest_report": latest.name if latest else None,
            "reports_dir": str(settings.reports_dir),
        }

    @app.get("/api/report/latest")
    def latest_report() -> dict[str, Any]:
        return _load_report()

    @app.get("/api/reports")
    def list_reports() -> list[dict[str, str]]:
        reports_dir = settings.reports_dir
        if not reports_dir.exists():
            return []
        out = []
        for f in sorted(reports_dir.glob("*.json"), reverse=True):
            out.append({"date": f.stem, "json": str(f), "markdown": str(reports_dir / f"{f.stem}.md")})
        return out

    @app.get("/api/report/{date}")
    def report_by_date(date: str) -> dict[str, Any]:
        path = settings.reports_dir / f"{date}.json"
        return _load_report(path)

    @app.post("/api/analyze")
    def trigger_analysis(offline: bool = False) -> JSONResponse:
        global _analysis_running, _analysis_error

        if _analysis_running:
            return JSONResponse({"status": "already_running"}, status_code=409)

        def _run() -> None:
            global _analysis_running, _analysis_error
            with _analysis_lock:
                _analysis_running = True
                _analysis_error = None
                try:
                    run_analysis(settings, offline=offline)
                except Exception as exc:
                    logger.exception("Analysis failed")
                    _analysis_error = str(exc)
                finally:
                    _analysis_running = False

        threading.Thread(target=_run, daemon=True).start()
        return JSONResponse({"status": "started", "started_at": datetime.now().isoformat()})

    @app.post("/api/import")
    async def import_holdings(
        file: UploadFile = File(...),
        kind: str = Form("auto"),
    ) -> dict[str, Any]:
        from grow_trade_assistant.groww_import import parse_groww_file, save_stocks_file
        from grow_trade_assistant.mf_config import save_mutual_fund_file

        name = file.filename or "upload.csv"
        suffix = Path(name).suffix.lower() or ".csv"
        if suffix not in {".csv", ".txt", ".xlsx", ".xlsm", ".numbers"}:
            raise HTTPException(status_code=400, detail="Use CSV, XLSX, or Numbers export from Groww.")
        dest_dir = settings.data_dir / "uploads"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"groww_import{suffix}"
        dest.write_bytes(await file.read())
        try:
            result = parse_groww_file(dest, kind=kind)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if result.stocks and settings.stocks_path:
            save_stocks_file(settings.stocks_path, result.stocks)
        if result.mutual_funds and settings.mutual_funds_path:
            save_mutual_fund_file(settings.mutual_funds_path, result.mutual_funds)
        if not result.stocks and not result.mutual_funds:
            raise HTTPException(status_code=400, detail="No holdings found in file.")
        return {
            "status": "imported",
            "kind": result.kind,
            "stocks": len(result.stocks),
            "mutual_funds": len(result.mutual_funds),
            "warnings": result.warnings,
        }

    return app
