from contextlib import asynccontextmanager
import os
from pathlib import Path
import subprocess
import sys

from fastapi import APIRouter, BackgroundTasks, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from tinydb_store import TinyDbStore

PREFIX = "/private/api/v2"
JSON_TYPE = "application/json"
UNSUPPORTED_MEDIA_TYPE = 415
NOT_ACCEPTABLE = 406
CONVERSION_TIMEOUT = 60
CONVERTER = Path(__file__).with_name("converter.py")
ACTIVE_STAGES = {"created", "running"}
DB_PATH = Path(__file__).resolve().parents[1] / "api_db.json"

router = APIRouter(prefix=PREFIX)


class ActorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: int
    platform: str
    user_agent: str


class InstructionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: int
    description: str
    tags: str


async def check_headers(request, call_next):
    content_type = request.headers.get("content-type", "")
    content_type = content_type.split(";", 1)[0].strip().lower()

    if request.method in {"POST", "PUT", "PATCH"}:
        if content_type != JSON_TYPE:
            return JSONResponse(
                {"error": "Content-Type must be application/json"},
                status_code=UNSUPPORTED_MEDIA_TYPE,
            )

    if request.headers.get("accept") != JSON_TYPE:
        return JSONResponse(
            {"error": "Accept must be application/json"},
            status_code=NOT_ACCEPTABLE,
        )

    return await call_next(request)


async def handle_value_error(request, error):
    return JSONResponse({"error": str(error)})


async def handle_validation_error(request, error):
    return JSONResponse({"error": "Invalid request parameters"})


def run_converter(input_path, output_path):
    subprocess.run(
        [sys.executable, "-X", "utf8", str(CONVERTER)],
        input=f"{input_path}\n{output_path}\n",
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
        timeout=CONVERSION_TIMEOUT,
    )


async def convert_instruction(store, uid, test_mode):
    instruction = store.update("Instruction", uid, stage="running")

    output = ""
    failure = ""
    stage = "done"

    try:
        source = Path(instruction["input"]).resolve()
        target = source.with_suffix(".jpg")

        if not test_mode:
            await run_in_threadpool(
                run_converter,
                str(source),
                str(target),
            )

        output = str(target)

    except (OSError, ValueError, subprocess.SubprocessError) as error:
        stage = "failed"
        failure = str(getattr(error, "stderr", None) or error).strip()

    store.update("Instruction", uid, stage=stage)

    store.create(
        "Response",
        uid,
        output=output,
        stage=stage,
        failure=failure,
        instruction=uid,
    )


@router.put("/submit/actor/{uid}")
async def put_actor_submit(
        request: Request,
        uid: int,
        platform: str,
        user_agent: str,
):
    return request.app.state.store.create(
        "Actor", uid, platform=platform, user_agent=user_agent,
    )


@router.delete("/pop/actor/{uid}")
async def delete_actor_pop(request: Request, uid: int):
    store = request.app.state.store
    if store.find("Instruction", actor=uid):
        raise ValueError("Actor has instructions")

    if not store.delete("Actor", "uid", uid):
        raise ValueError("Actor not found")

    return {"deleted": uid}


@router.get("/show/actor")
async def get_actor_show(
        request: Request,
        uid: int | None = None,
        platform: str | None = None,
        user_agent: str | None = None,
):
    return request.app.state.store.find(
        "Actor", uid=uid, platform=platform, user_agent=user_agent,
    )


@router.post("/revise/actor")
async def post_actor_revise(request: Request, data: ActorUpdate):
    return request.app.state.store.update(
        "Actor",
        data.uid,
        platform=data.platform,
        user_agent=data.user_agent,
    )


@router.put("/submit/instruction/{uid}")
async def put_instruction_submit(
        request: Request,
        background_tasks: BackgroundTasks,
        uid: int,
        input_text: str = Query(alias="input"),
        actor: int = Query(),
        description: str = "PNG to JPEG",
        tags: str = "png,jpeg",
):
    if "\n" in input_text or "\r" in input_text:
        raise ValueError("Input path must not contain line breaks")

    store = request.app.state.store
    store.get("Actor", actor)
    instruction = store.create(
        "Instruction",
        uid,
        input=input_text,
        actor=actor,
        description=description,
        tags=tags,
        stage="created",
    )

    background_tasks.add_task(
        convert_instruction,
        store,
        uid,
        request.app.state.test_mode,
    )

    return instruction


@router.delete("/pop/instruction/{uid}")
async def delete_instruction_pop(request: Request, uid: int):
    store = request.app.state.store
    instruction = store.get("Instruction", uid)

    if instruction["stage"] in ACTIVE_STAGES:
        raise ValueError("Instruction is still running")

    store.delete("Response", "instruction", uid)
    store.delete("Instruction", "uid", uid)

    return {"deleted": uid}


@router.get("/show/instruction/{actor}")
async def get_instruction_show(
        request: Request,
        actor: int,
        uid: int | None = None,
        stage: str | None = None,
):
    return request.app.state.store.find(
        "Instruction", actor=actor, uid=uid, stage=stage,
    )


@router.post("/revise/instruction")
async def post_instruction_revise(request: Request, data: InstructionUpdate):
    return request.app.state.store.update(
        "Instruction",
        data.uid,
        description=data.description,
        tags=data.tags,
    )


@router.get("/show/response/{instruction}")
async def get_response_show(
        request: Request,
        instruction: int,
        stage: str | None = None,
):
    return request.app.state.store.find(
        "Response", instruction=instruction, stage=stage,
    )


@router.get("/show/report")
async def get_report_show(request: Request):
    return request.app.state.store.get_recent_responses()


def create_app(test_mode=False, db_path=DB_PATH):
    @asynccontextmanager
    async def lifespan(application):
        store = TinyDbStore(db_path)
        application.state.store = store
        try:
            yield
        finally:
            store.close()

    application = FastAPI(
        title="PNG to JPEG",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    application.state.test_mode = test_mode
    application.middleware("http")(check_headers)

    application.add_exception_handler(
        ValueError,
        handle_value_error,
    )

    application.add_exception_handler(
        RequestValidationError,
        handle_validation_error,
    )

    application.include_router(router)

    return application


app = create_app(
    test_mode=os.environ.get("API_TEST_MODE") == "1",
)
