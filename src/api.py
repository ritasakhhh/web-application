import os
from pathlib import Path
import subprocess
import sys

from fastapi import APIRouter, BackgroundTasks, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

import first_step

PREFIX = "/private/api/v2"
JSON_TYPE = "application/json"
UNSUPPORTED_MEDIA_TYPE = 415
NOT_ACCEPTABLE = 406
CONVERSION_TIMEOUT = 60
CONVERTER = Path(__file__).with_name("converter.py")
ACTIVE_STAGES = {"created", "running"}

ACTOR_FIELDS = (
    "uid",
    "datetime",
    "platform",
    "user_agent",
)

INSTRUCTION_FIELDS = (
    "uid",
    "datetime",
    "input",
    "actor",
    "description",
    "tags",
    "stage",
)

RESPONSE_FIELDS = (
    "uid",
    "datetime",
    "output",
    "stage",
    "failure",
    "instruction",
)

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


def select_records(records, fields, **filters):
    filters = {
        key: value for key, value in filters.items() if value is not None
    }

    result = []

    for record in records:
        item = dict(zip(fields, record))

        if all(item[key] == value for key, value in filters.items()):
            result.append(item)

    return result


def get_instruction(uid):
    records = select_records(
        first_step.get_instructions(),
        INSTRUCTION_FIELDS,
        uid=uid,
    )

    if not records:
        raise ValueError("Instruction not found")

    return records[0]


def revise_instruction(uid, **changes):
    record = get_instruction(uid)
    record.update(changes)

    updated = first_step.update_instruction(
        uid,
        record["input"],
        record["actor"],
        record["description"],
        record["tags"],
        record["stage"],
    )

    return dict(zip(INSTRUCTION_FIELDS, updated))


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


async def convert_instruction(uid, test_mode):
    instruction = revise_instruction(uid, stage="running")

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

    revise_instruction(uid, stage=stage)

    first_step.create_response(
        output,
        stage,
        failure,
        uid,
        uid=uid,
    )


@router.put("/submit/actor/{uid}")
async def put_actor_submit(
        uid: int,
        platform: str,
        user_agent: str,
):
    actor = first_step.create_actor(
        platform,
        user_agent,
        uid=uid,
    )

    return dict(zip(ACTOR_FIELDS, actor))


@router.delete("/pop/actor/{uid}")
async def delete_actor_pop(uid: int):
    if any(item[3] == uid for item in first_step.get_instructions()):
        raise ValueError("Actor has instructions")

    first_step.delete_actor(uid)

    return {"deleted": uid}


@router.get("/show/actor")
async def get_actor_show(
        uid: int | None = None,
        platform: str | None = None,
        user_agent: str | None = None,
):
    return select_records(
        first_step.get_actors(),
        ACTOR_FIELDS,
        uid=uid,
        platform=platform,
        user_agent=user_agent,
    )


@router.post("/revise/actor")
async def post_actor_revise(data: ActorUpdate):
    actor = first_step.update_actor(
        data.uid,
        data.platform,
        data.user_agent,
    )

    return dict(zip(ACTOR_FIELDS, actor))


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

    instruction = first_step.create_instruction(
        input_text,
        actor,
        description,
        tags,
        "created",
        uid=uid,
    )

    background_tasks.add_task(
        convert_instruction,
        uid,
        request.app.state.test_mode,
    )

    return dict(zip(INSTRUCTION_FIELDS, instruction))


@router.delete("/pop/instruction/{uid}")
async def delete_instruction_pop(uid: int):
    instruction = get_instruction(uid)

    if instruction["stage"] in ACTIVE_STAGES:
        raise ValueError("Instruction is still running")

    responses = first_step.get_responses().copy()

    for response in responses:
        if response[5] == uid:
            first_step.delete_response(response[0])

    first_step.delete_instruction(uid)

    return {"deleted": uid}


@router.get("/show/instruction/{actor}")
async def get_instruction_show(
        actor: int,
        uid: int | None = None,
        stage: str | None = None,
):
    return select_records(
        first_step.get_instructions(),
        INSTRUCTION_FIELDS,
        actor=actor,
        uid=uid,
        stage=stage,
    )


@router.post("/revise/instruction")
async def post_instruction_revise(data: InstructionUpdate):
    return revise_instruction(
        data.uid,
        description=data.description,
        tags=data.tags,
    )


@router.get("/show/response/{instruction}")
async def get_response_show(
        instruction: int,
        stage: str | None = None,
):
    return select_records(
        first_step.get_responses(),
        RESPONSE_FIELDS,
        instruction=instruction,
        stage=stage,
    )


@router.get("/show/report")
async def get_report_show():
    return [
        {"description": description, "output": output}
        for description, output in first_step.get_recent_responses()
    ]


def create_app(test_mode=False):
    application = FastAPI(
        title="PNG to JPEG",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
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
