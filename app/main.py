from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import authenticate, get_user_role, has_unlimited_tests, is_authenticated, session_secret
from app.llm_service import available_models
from app.pipeline import run_verification
from app.schemas import ApplicationFields, UsageStatus
from app.usage import UsageLimitExceeded, get_usage_status, reserve_tests

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Treasury Label Verify", version="0.1.0")
app.add_middleware(SessionMiddleware, secret_key=session_secret(), https_only=False)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

GOV_WARNING_DEFAULT = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)


def require_auth(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Authentication required")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))
    role = authenticate(username, password)
    if not role:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "ACCESS DENIED: invalid credentials"},
            status_code=401,
        )
    request.session["authenticated"] = True
    request.session["role"] = role
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, _auth=Depends(require_auth)):
    unlimited = has_unlimited_tests(request)
    usage = get_usage_status(unlimited=unlimited)
    models = available_models()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "usage": usage,
            "user_role": get_user_role(request),
            "unlimited": unlimited,
            "models": models,
            "default_model": models[0] if models else "gpt-4.1-mini",
            "gov_warning": GOV_WARNING_DEFAULT,
        },
    )


SAMPLES_DIR = BASE_DIR.parent / "samples"
LABELS_DIR = SAMPLES_DIR / "labels"


@app.get("/samples/applications.json")
def sample_applications(_auth=Depends(require_auth)):
    path = SAMPLES_DIR / "applications.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Sample applications not found")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


@app.get("/samples/labels/{filename}")
def sample_label(filename: str, _auth=Depends(require_auth)):
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = LABELS_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Sample label not found")
    return FileResponse(path)


@app.get("/api/usage")
def api_usage(request: Request, _auth=Depends(require_auth)) -> UsageStatus:
    return get_usage_status(unlimited=has_unlimited_tests(request))


@app.post("/api/verify")
async def api_verify(
    request: Request,
    image: UploadFile = File(...),
    brand_name: str = Form(...),
    class_type: str = Form(...),
    alcohol_content: str = Form(...),
    net_contents: str = Form(...),
    government_warning: str = Form(...),
    llm_model: str = Form(...),
    _auth=Depends(require_auth),
):
    try:
        reserve_tests(1, unlimited=has_unlimited_tests(request))
    except UsageLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    image_bytes = await image.read()
    application = ApplicationFields(
        brand_name=brand_name.strip(),
        class_type=class_type.strip(),
        alcohol_content=alcohol_content.strip(),
        net_contents=net_contents.strip(),
        government_warning=government_warning.strip(),
    )
    try:
        result = run_verification(
            image_bytes=image_bytes,
            application=application,
            filename=image.filename or "upload",
            llm_model=llm_model,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Verification failed: {exc}",
        ) from exc
    return JSONResponse(result.model_dump())


@app.post("/api/batch/stream")
async def api_batch_stream(
    request: Request,
    images: list[UploadFile] = File(...),
    applications_json: str = Form(...),
    llm_model: str = Form(...),
    _auth=Depends(require_auth),
):
    try:
        apps_raw = json.loads(applications_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid applications_json") from exc

    if len(images) != len(apps_raw):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Image count ({len(images)}) must match application count ({len(apps_raw)}). "
                "Click LOAD SAMPLE JSON, then select the same number of label images in order."
            ),
        )

    try:
        reserve_tests(len(images), unlimited=has_unlimited_tests(request))
    except UsageLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    async def event_generator():
        total = len(images)
        for idx, (image, app_data) in enumerate(zip(images, apps_raw), start=1):
            prefix = f"[{idx:03d}/{total:03d}]"
            yield f"data: {json.dumps({'type': 'log', 'message': f'{prefix} OCR...'})}\n\n"
            image_bytes = await image.read()
            application = ApplicationFields(**app_data)
            result = run_verification(
                image_bytes=image_bytes,
                application=application,
                filename=image.filename or f"label_{idx}",
                llm_model=llm_model,
            )
            payload = {
                "type": "result",
                "index": idx,
                "total": total,
                "result": result.model_dump(),
            }
            yield f"data: {json.dumps(payload)}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'usage': get_usage_status(unlimited=has_unlimited_tests(request)).model_dump()})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.on_event("startup")
def warm_ocr():
    if os.getenv("WARM_OCR", "1") == "1":
        try:
            from app.ocr_service import get_reader

            get_reader()
        except Exception:
            pass
