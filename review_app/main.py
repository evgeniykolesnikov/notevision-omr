"""FastAPI application for protected OMR expert review."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from review_app.auth import (
    COOKIE_NAME,
    REVIEWER_COOKIE_NAME,
    build_auth_token,
    build_reviewer_session,
    read_reviewer_session,
    verify_auth_token,
    verify_password,
)
from review_app.database import (
    DEFAULT_DB_PATH,
    adjacent_failure_ids,
    adjacent_item_numbers,
    get_failure_review,
    get_or_create_reviewer,
    get_item,
    get_reviewer,
    init_db,
    list_failure_reviews,
    list_items,
    save_failure_review,
    save_review,
)
from review_app.dashboard import (
    available_reports,
    dashboard_audio_path,
    dashboard_artifact_path,
    load_dashboard_data,
    load_inbox_overview,
    load_page_detail,
    report_path,
)
from review_app.export_csv import build_export_csv
from review_app.export_failures import build_failure_export_csv
from review_app.failure_schemas import validate_failure_submission
from review_app.media_files import download_filename, find_review_result_file
from review_app.models import (
    FAILURE_DECISIONS,
    FAILURE_REASONS,
    FAILURE_REVIEW_STATUSES,
    REVIEW_STATUSES,
)
from review_app.schemas import resolve_review_metadata, validate_review_submission

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
DEFAULT_PACKAGE_DIR = PROJECT_ROOT / "outputs" / "expert_review_for_send"


async def _read_urlencoded_form(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" not in content_type:
        raise HTTPException(status_code=415, detail="Unsupported form encoding")
    parsed = parse_qs(
        (await request.body()).decode("utf-8"),
        keep_blank_values=True,
    )
    return {key: values[-1] for key, values in parsed.items()}


def create_app(
    *,
    db_path: Path | None = None,
    package_dir: Path | None = None,
    password: str | None = None,
    project_root: Path | None = None,
) -> FastAPI:
    selected_project_root = Path(project_root or PROJECT_ROOT).resolve()
    selected_db = Path(
        db_path or os.getenv("REVIEW_APP_DB", str(DEFAULT_DB_PATH))
    ).resolve()
    selected_package = Path(
        package_dir
        or os.getenv("REVIEW_PACKAGE_DIR", str(DEFAULT_PACKAGE_DIR))
    ).resolve()
    selected_password = (
        password
        if password is not None
        else os.getenv("REVIEW_APP_PASSWORD", "")
    )
    init_db(selected_db)

    app = FastAPI(title="NoteVision OMR Expert Review")
    app.state.db_path = selected_db
    app.state.package_dir = selected_package
    app.state.project_root = selected_project_root
    app.state.password = selected_password
    templates = Jinja2Templates(directory=APP_DIR / "templates")
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

    def authenticated(request: Request) -> bool:
        return verify_auth_token(
            request.cookies.get(COOKIE_NAME),
            app.state.password,
        )

    def current_reviewer(request: Request) -> dict[str, object] | None:
        reviewer_id = read_reviewer_session(
            request.cookies.get(REVIEWER_COOKIE_NAME), app.state.password
        )
        if reviewer_id is None:
            return None
        return get_reviewer(app.state.db_path, reviewer_id)

    def session_ready(request: Request) -> bool:
        return authenticated(request) and current_reviewer(request) is not None

    def establish_session(
        reviewer: dict[str, object],
        next_path: str,
    ) -> RedirectResponse:
        response = RedirectResponse(next_path, status_code=303)
        response.set_cookie(
            COOKIE_NAME,
            build_auth_token(app.state.password),
            httponly=True,
            samesite="strict",
            secure=False,
            max_age=12 * 60 * 60,
        )
        response.set_cookie(
            REVIEWER_COOKIE_NAME,
            build_reviewer_session(int(reviewer["id"]), app.state.password),
            httponly=True,
            samesite="strict",
            secure=False,
            max_age=12 * 60 * 60,
        )
        return response

    def login_redirect(request: Request) -> RedirectResponse:
        path = request.url.path
        return RedirectResponse(
            url=f"/login?next={path}",
            status_code=303,
        )

    def render_review(
        request: Request,
        item: dict[str, object],
        *,
        errors: list[str] | None = None,
        values: dict[str, object] | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        previous_number, next_number = adjacent_item_numbers(
            app.state.db_path,
            int(item["item_number"]),
        )
        downloads = {
            kind: find_review_result_file(
                item,
                kind=kind,
                package_dir=app.state.package_dir,
                project_root=app.state.project_root,
            )
            is not None
            for kind in ("midi", "mxl")
        }
        return templates.TemplateResponse(
            request=request,
            name="review.html",
            context={
                "item": item,
                "values": values or item,
                "errors": errors or [],
                "reviewer_name": current_reviewer(request)["name"],
                "previous_number": previous_number,
                "next_number": next_number,
                "downloads": downloads,
            },
            status_code=status_code,
        )

    def render_failure(
        request: Request,
        failure: dict[str, object],
        *,
        errors: list[str] | None = None,
        values: dict[str, object] | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        previous_id, next_id = adjacent_failure_ids(
            app.state.db_path,
            int(failure["id"]),
        )
        reviewer = current_reviewer(request)
        assert reviewer is not None
        return templates.TemplateResponse(
            request=request,
            name="failure_review.html",
            context={
                "failure": failure,
                "values": values or failure,
                "errors": errors or [],
                "reviewer_name": reviewer["name"],
                "failure_reasons": FAILURE_REASONS,
                "failure_decisions": FAILURE_DECISIONS,
                "previous_id": previous_id,
                "next_id": next_id,
            },
            status_code=status_code,
        )

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(
        request: Request,
        next: str = "/",
    ) -> Response:
        if session_ready(request):
            return RedirectResponse("/", status_code=303)
        safe_next = (
            next if next.startswith("/") and not next.startswith("//") else "/"
        )
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "",
                "next": safe_next,
                "password_configured": bool(app.state.password),
                "reviewer_name": "",
            },
        )

    @app.post("/login")
    async def login(request: Request) -> Response:
        form = await _read_urlencoded_form(request)
        next_path = form.get("next", "/")
        if not next_path.startswith("/") or next_path.startswith("//"):
            next_path = "/"
        if not app.state.password:
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={
                    "error": "REVIEW_APP_PASSWORD не настроен.",
                    "next": next_path,
                    "password_configured": False,
                    "reviewer_name": form.get("reviewer_name", ""),
                },
                status_code=503,
            )
        if not verify_password(form.get("password", ""), app.state.password):
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={
                    "error": "Неверный пароль.",
                    "next": next_path,
                    "password_configured": True,
                    "reviewer_name": form.get("reviewer_name", ""),
                },
                status_code=401,
            )
        reviewer_name = form.get("reviewer_name", "")
        try:
            reviewer, _ = get_or_create_reviewer(
                app.state.db_path,
                reviewer_name,
            )
        except ValueError:
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={
                    "error": "Укажите имя эксперта.",
                    "next": next_path,
                    "password_configured": True,
                    "reviewer_name": reviewer_name,
                },
                status_code=422,
            )
        return establish_session(reviewer, next_path)

    @app.post("/logout")
    async def logout() -> RedirectResponse:
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(COOKIE_NAME)
        response.delete_cookie(REVIEWER_COOKIE_NAME)
        return response

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, status: str = "all") -> HTMLResponse:
        if not session_ready(request):
            return login_redirect(request)
        reviewer = current_reviewer(request)
        assert reviewer is not None
        selected_status = status if status in REVIEW_STATUSES else "all"
        items = list_items(
            app.state.db_path,
            int(reviewer["id"]),
            None if selected_status == "all" else selected_status,
        )
        all_items = list_items(app.state.db_path, int(reviewer["id"]))
        counts = {
            value: sum(
                item["review_status"] == value for item in all_items
            )
            for value in REVIEW_STATUSES
        }
        counts["all"] = len(all_items)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "items": items,
                "selected_status": selected_status,
                "counts": counts,
                "reviewer_name": reviewer["name"],
            },
        )

    @app.get("/documents", response_class=HTMLResponse)
    async def documents_page(request: Request) -> HTMLResponse:
        if not session_ready(request):
            return login_redirect(request)
        reviewer = current_reviewer(request)
        assert reviewer is not None
        dashboard = load_dashboard_data(app.state.project_root)
        return templates.TemplateResponse(
            request=request,
            name="documents.html",
            context={
                "documents": dashboard["documents"],
                "reviewer_name": reviewer["name"],
            },
        )

    @app.get("/documents/{doc_id}", response_class=HTMLResponse)
    async def document_detail(request: Request, doc_id: str) -> HTMLResponse:
        if not session_ready(request):
            return login_redirect(request)
        reviewer = current_reviewer(request)
        assert reviewer is not None
        dashboard = load_dashboard_data(app.state.project_root)
        document = dashboard["document_map"].get(doc_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return templates.TemplateResponse(
            request=request,
            name="document_detail.html",
            context={
                "document": document,
                "pages": dashboard["pages_by_doc"].get(doc_id, []),
                "reviewer_name": reviewer["name"],
            },
        )

    @app.get(
        "/documents/{doc_id}/pages/{page_index}",
        response_class=HTMLResponse,
    )
    async def document_page_detail(
        request: Request,
        doc_id: str,
        page_index: int,
    ) -> HTMLResponse:
        if not session_ready(request):
            return login_redirect(request)
        reviewer = current_reviewer(request)
        assert reviewer is not None
        detail = load_page_detail(
            app.state.project_root,
            app.state.db_path,
            app.state.package_dir,
            doc_id,
            page_index,
            int(reviewer["id"]),
        )
        if detail is None:
            raise HTTPException(status_code=404, detail="Page not found")
        return templates.TemplateResponse(
            request=request,
            name="page_detail.html",
            context={
                **detail,
                "reviewer_name": reviewer["name"],
            },
        )

    @app.get("/inbox", response_class=HTMLResponse)
    async def inbox_page(request: Request) -> HTMLResponse:
        if not session_ready(request):
            return login_redirect(request)
        reviewer = current_reviewer(request)
        assert reviewer is not None
        return templates.TemplateResponse(
            request=request,
            name="inbox.html",
            context={
                "overview": load_inbox_overview(app.state.project_root),
                "reviewer_name": reviewer["name"],
            },
        )

    @app.get("/reports", response_class=HTMLResponse)
    async def reports_page(request: Request) -> HTMLResponse:
        if not session_ready(request):
            return login_redirect(request)
        reviewer = current_reviewer(request)
        assert reviewer is not None
        return templates.TemplateResponse(
            request=request,
            name="reports.html",
            context={
                "reports": available_reports(app.state.project_root),
                "reviewer_name": reviewer["name"],
            },
        )

    @app.get("/review/{item_number}", response_class=HTMLResponse)
    async def review_page(request: Request, item_number: int) -> HTMLResponse:
        if not session_ready(request):
            return login_redirect(request)
        reviewer = current_reviewer(request)
        assert reviewer is not None
        item = get_item(app.state.db_path, item_number, int(reviewer["id"]))
        if item is None:
            raise HTTPException(status_code=404, detail="Review item not found")
        return render_review(request, item)

    @app.post("/review/{item_number}", response_class=HTMLResponse)
    async def submit_review(request: Request, item_number: int) -> Response:
        if not session_ready(request):
            return login_redirect(request)
        reviewer = current_reviewer(request)
        assert reviewer is not None
        item = get_item(app.state.db_path, item_number, int(reviewer["id"]))
        if item is None:
            raise HTTPException(status_code=404, detail="Review item not found")
        form = await _read_urlencoded_form(request)
        action = form.get("action", "draft")
        complete = action == "complete"
        reviewer_name, selected_review_date = resolve_review_metadata(
            str(reviewer["name"]),
            complete=complete,
            existing_review_date=str(item.get("review_date", "")),
        )
        submission, errors = validate_review_submission(
            form,
            complete=complete,
            reviewer=reviewer_name,
            review_date=selected_review_date,
        )
        values = submission.as_dict()
        if errors:
            return render_review(
                request,
                item,
                errors=errors,
                values={**item, **values},
                status_code=422,
            )
        save_review(
            app.state.db_path,
            item_number,
            int(reviewer["id"]),
            values,
            "completed" if complete else "draft",
        )
        return RedirectResponse(f"/review/{item_number}", status_code=303)

    @app.get("/failures", response_class=HTMLResponse)
    async def failure_list(
        request: Request,
        status: str = "all",
    ) -> HTMLResponse:
        if not session_ready(request):
            return login_redirect(request)
        selected_status = (
            status
            if status in {*FAILURE_REVIEW_STATUSES, "unknown_failure"}
            else "all"
        )
        failures = list_failure_reviews(
            app.state.db_path,
            None if selected_status == "all" else selected_status,
        )
        all_failures = list_failure_reviews(app.state.db_path)
        counts = {
            "all": len(all_failures),
            "draft": sum(
                row["review_status"] == "draft" for row in all_failures
            ),
            "reviewed": sum(
                row["review_status"] == "reviewed" for row in all_failures
            ),
            "unknown_failure": sum(
                row["failure_reason"] == "unknown_failure"
                for row in all_failures
            ),
        }
        reviewer = current_reviewer(request)
        assert reviewer is not None
        return templates.TemplateResponse(
            request=request,
            name="failures.html",
            context={
                "failures": failures,
                "counts": counts,
                "selected_status": selected_status,
                "reviewer_name": reviewer["name"],
            },
        )

    @app.get("/failures/{failure_id}", response_class=HTMLResponse)
    async def failure_page(
        request: Request,
        failure_id: int,
    ) -> HTMLResponse:
        if not session_ready(request):
            return login_redirect(request)
        failure = get_failure_review(app.state.db_path, failure_id)
        if failure is None:
            raise HTTPException(status_code=404, detail="Failure not found")
        return render_failure(request, failure)

    @app.post("/failures/{failure_id}", response_class=HTMLResponse)
    async def submit_failure(
        request: Request,
        failure_id: int,
    ) -> Response:
        if not session_ready(request):
            return login_redirect(request)
        failure = get_failure_review(app.state.db_path, failure_id)
        if failure is None:
            raise HTTPException(status_code=404, detail="Failure not found")
        reviewer = current_reviewer(request)
        assert reviewer is not None
        form = await _read_urlencoded_form(request)
        reviewed = form.get("action") == "reviewed"
        values, errors = validate_failure_submission(form, reviewed=reviewed)
        if errors:
            return render_failure(
                request,
                failure,
                errors=errors,
                values={**failure, **values},
                status_code=422,
            )
        save_failure_review(
            app.state.db_path,
            failure_id,
            values,
            str(reviewer["name"]),
            "reviewed" if reviewed else "draft",
        )
        return RedirectResponse(f"/failures/{failure_id}", status_code=303)

    def protected_file(
        request: Request,
        item_number: int,
        filename: str,
    ) -> Response:
        if not session_ready(request):
            return login_redirect(request)
        package_root = app.state.package_dir.resolve()
        candidate = (package_root / filename).resolve()
        try:
            candidate.relative_to(package_root)
        except ValueError as error:
            raise HTTPException(status_code=404, detail="Media not found") from error
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="Media not found")
        return FileResponse(
            candidate,
            headers={
                "Cache-Control": "public, max-age=3600",
                "Accept-Ranges": "bytes",
            },
        )

    def result_download(
        request: Request,
        item: dict[str, object],
        kind: str,
    ) -> Response:
        if not session_ready(request):
            return login_redirect(request)
        candidate = find_review_result_file(
            item,
            kind=kind,
            package_dir=app.state.package_dir,
            project_root=app.state.project_root,
        )
        if candidate is None:
            raise HTTPException(status_code=404, detail="Result file not found")
        return FileResponse(
            candidate,
            filename=download_filename(item, kind),
            media_type="audio/midi" if kind == "midi" else "application/octet-stream",
            headers={
                "Cache-Control": "private, max-age=3600",
                "Accept-Ranges": "bytes",
            },
        )

    def protected_project_file(
        request: Request,
        relative_path: str,
        allowed_root: Path,
    ) -> Response:
        if not session_ready(request):
            return login_redirect(request)
        root = allowed_root.resolve()
        candidate = (app.state.project_root / relative_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise HTTPException(status_code=404, detail="File not found") from error
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(
            candidate,
            headers={
                "Cache-Control": "public, max-age=3600",
                "Accept-Ranges": "bytes",
            },
        )

    @app.get("/media/{item_number}/scan")
    async def scan_media(request: Request, item_number: int) -> Response:
        item = get_item(app.state.db_path, item_number)
        if item is None:
            raise HTTPException(status_code=404, detail="Review item not found")
        return protected_file(
            request,
            item_number,
            str(item["scan_path"]),
        )

    @app.get("/media/{item_number}/audio")
    async def audio_media(
        request: Request,
        item_number: int,
        download: bool = False,
    ) -> Response:
        item = get_item(app.state.db_path, item_number)
        if item is None:
            raise HTTPException(status_code=404, detail="Review item not found")
        response = protected_file(
            request,
            item_number,
            str(item["audio_path"]),
        )
        if download and isinstance(response, FileResponse):
            response.headers["Content-Disposition"] = (
                f'attachment; filename="notevision_{item["doc_id"]}_'
                f'page_{int(item["page_index"]):03d}_audio.mp3"'
            )
        return response

    @app.get("/media/{item_number}/track/{track_number}")
    async def track_media(
        request: Request,
        item_number: int,
        track_number: int,
        download: bool = False,
    ) -> Response:
        item = get_item(app.state.db_path, item_number)
        if item is None:
            raise HTTPException(status_code=404, detail="Review item not found")
        track_paths = item["track_paths"]
        if track_number < 1 or track_number > len(track_paths):
            raise HTTPException(status_code=404, detail="Track not found")
        response = protected_file(
            request,
            item_number,
            str(track_paths[track_number - 1]),
        )
        if download and isinstance(response, FileResponse):
            response.headers["Content-Disposition"] = (
                f'attachment; filename="notevision_{item["doc_id"]}_'
                f'page_{int(item["page_index"]):03d}_'
                f'track_{track_number:02d}.mp3"'
            )
        return response

    @app.get("/media/{item_number}/midi")
    async def midi_download(request: Request, item_number: int) -> Response:
        if not session_ready(request):
            return login_redirect(request)
        item = get_item(app.state.db_path, item_number)
        if item is None:
            raise HTTPException(status_code=404, detail="Review item not found")
        return result_download(request, item, "midi")

    @app.get("/media/{item_number}/mxl")
    async def mxl_download(request: Request, item_number: int) -> Response:
        if not session_ready(request):
            return login_redirect(request)
        item = get_item(app.state.db_path, item_number)
        if item is None:
            raise HTTPException(status_code=404, detail="Review item not found")
        return result_download(request, item, "mxl")

    @app.get("/document-media/{doc_id}/{page_index}/{kind}")
    async def document_media(
        request: Request,
        doc_id: str,
        page_index: int,
        kind: str,
    ) -> Response:
        if not session_ready(request):
            return login_redirect(request)
        if kind not in {"image", "midi", "mxl", "audio"}:
            raise HTTPException(status_code=404, detail="Artifact not found")
        candidate = (
            dashboard_audio_path(
                app.state.project_root,
                app.state.db_path,
                app.state.package_dir,
                doc_id,
                page_index,
            )
            if kind == "audio"
            else dashboard_artifact_path(
                app.state.project_root,
                doc_id,
                page_index,
                kind,
            )
        )
        if candidate is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        if kind in {"image", "audio"}:
            return FileResponse(
                candidate,
                headers={
                    "Cache-Control": "public, max-age=3600",
                    "Accept-Ranges": "bytes",
                },
            )
        extension = "mid" if kind == "midi" else "mxl"
        return FileResponse(
            candidate,
            filename=f"notevision_{doc_id}_page_{page_index:03d}.{extension}",
            media_type="audio/midi" if kind == "midi" else "application/octet-stream",
            headers={
                "Cache-Control": "private, max-age=3600",
                "Accept-Ranges": "bytes",
            },
        )

    @app.get("/document-media/{doc_id}/{page_index}/track/{track_number}")
    async def document_track_media(
        request: Request,
        doc_id: str,
        page_index: int,
        track_number: int,
        download: bool = False,
    ) -> Response:
        if not session_ready(request):
            return login_redirect(request)
        candidate = dashboard_audio_path(
            app.state.project_root,
            app.state.db_path,
            app.state.package_dir,
            doc_id,
            page_index,
            track_number,
        )
        if candidate is None:
            raise HTTPException(status_code=404, detail="Track not found")
        return FileResponse(
            candidate,
            filename=(
                f"notevision_{doc_id}_page_{page_index:03d}_"
                f"track_{track_number:02d}{candidate.suffix}"
                if download
                else None
            ),
            headers={
                "Cache-Control": "private, max-age=3600",
                "Accept-Ranges": "bytes",
            },
        )

    @app.get("/reports/file/{report_key}")
    async def report_file(request: Request, report_key: str) -> Response:
        if not session_ready(request):
            return login_redirect(request)
        candidate = report_path(app.state.project_root, report_key)
        if candidate is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return FileResponse(candidate)

    @app.get("/failure-media/{failure_id}/scan")
    async def failure_scan_media(
        request: Request,
        failure_id: int,
    ) -> Response:
        if not session_ready(request):
            return login_redirect(request)
        failure = get_failure_review(app.state.db_path, failure_id)
        if failure is None:
            raise HTTPException(status_code=404, detail="Failure not found")
        return protected_project_file(
            request,
            str(failure["image_path"]),
            app.state.project_root / "outputs" / "pages",
        )

    @app.get("/failure-media/{failure_id}/log")
    async def failure_log_media(
        request: Request,
        failure_id: int,
    ) -> Response:
        if not session_ready(request):
            return login_redirect(request)
        failure = get_failure_review(app.state.db_path, failure_id)
        if failure is None or not failure["log_path"]:
            raise HTTPException(status_code=404, detail="Audiveris log not found")
        return protected_project_file(
            request,
            str(failure["log_path"]),
            app.state.project_root / "outputs" / "omr_300dpi",
        )

    @app.get("/export/expert_review.csv")
    async def export_csv(request: Request) -> Response:
        if not session_ready(request):
            return login_redirect(request)
        content = "\ufeff" + build_export_csv(app.state.db_path)
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": (
                    'attachment; filename="expert_review.csv"'
                )
            },
        )

    @app.get("/export/failure_review.csv")
    async def export_failure_csv(request: Request) -> Response:
        if not session_ready(request):
            return login_redirect(request)
        content = "\ufeff" + build_failure_export_csv(app.state.db_path)
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": (
                    'attachment; filename="failure_review.csv"'
                )
            },
        )

    return app


app = create_app()
