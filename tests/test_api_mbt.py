from contextlib import ExitStack, contextmanager
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    rule,
)
from PIL import Image

import first_step
from api import create_app
from api_client import ApiClient

INITIAL_TIME = 1_700_000_000
REPORT_SECONDS = 360
MAX_EXAMPLES = 20
STATEFUL_STEPS = 25
EXAMPLES = 12
IMAGE_SIZE = (12, 8)

OK = 200
METHOD_NOT_ALLOWED = 405
UNSUPPORTED_MEDIA_TYPE = 415
NOT_ACCEPTABLE = 406
JSON_TYPE = "application/json"

IDS = st.integers(min_value=0, max_value=4)
OPTIONAL_ID = st.one_of(st.none(), IDS)
TEXT = st.text(alphabet="abc XYZ012_абв", min_size=0, max_size=10)
OPTIONAL_TEXT = st.one_of(st.none(), TEXT)
STAGES = st.sampled_from([None, "created", "running", "done", "failed"])
METHODS = st.sampled_from(["GET", "DELETE", "POST", "PUT", "PATCH"])
MEDIA_TYPES = st.sampled_from([None, JSON_TYPE, "text/plain"])


@contextmanager
def running_api(test_mode=True):
    first_step.actors.clear()
    first_step.instructions.clear()
    first_step.responses.clear()

    with TestClient(create_app(test_mode=test_mode)) as session:
        yield ApiClient("http://testserver", session=session)


def expected_status(method, content_type, accept):
    if method in {"POST", "PUT", "PATCH"} and content_type != JSON_TYPE:
        return UNSUPPORTED_MEDIA_TYPE
    if accept != JSON_TYPE:
        return NOT_ACCEPTABLE
    if method == "PATCH":
        return METHOD_NOT_ALLOWED
    return OK


class ApiStateMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()

        self.resources = ExitStack()
        self.clock = self.resources.enter_context(patch(
            "first_step.get_current_time",
            return_value=INITIAL_TIME,
        ))
        self.client = self.resources.enter_context(running_api())

        self.actors = {}
        self.instructions = {}
        self.responses = {}

    def teardown(self):
        self.resources.close()

    @initialize()
    def initial_records(self):
        self.submit_actor(0, "base", "agent")
        self.submit_instruction(0, 0, "base", "png")

    @rule(uid=IDS, platform=TEXT, user_agent=TEXT)
    def submit_actor(self, uid, platform, user_agent):
        result = self.client.put_actor_submit(uid, platform, user_agent)

        if uid in self.actors:
            assert result == {"error": "Identifier already exists"}
        else:
            expected = {
                "uid": uid,
                "datetime": self.clock.return_value,
                "platform": platform,
                "user_agent": user_agent,
            }
            assert result == expected
            self.actors[uid] = expected

    @rule(uid=IDS)
    def pop_actor(self, uid):
        result = self.client.delete_actor_pop(uid)

        if any(item["actor"] == uid for item in self.instructions.values()):
            assert result == {"error": "Actor has instructions"}
        elif uid not in self.actors:
            assert result == {"error": "Actor not found"}
        else:
            assert result == {"deleted": uid}
            del self.actors[uid]

    @rule(uid=OPTIONAL_ID, platform=OPTIONAL_TEXT, user_agent=OPTIONAL_TEXT)
    def show_actor(self, uid, platform, user_agent):
        expected = []

        for actor in self.actors.values():
            matches = (
                (uid is None or actor["uid"] == uid)
                and (platform is None or actor["platform"] == platform)
                and (user_agent is None or actor["user_agent"] == user_agent)
            )
            if matches:
                expected.append(actor)

        assert self.client.get_actor_show(
            uid=uid,
            platform=platform,
            user_agent=user_agent,
        ) == expected

    @rule(uid=IDS, platform=TEXT, user_agent=TEXT)
    def revise_actor(self, uid, platform, user_agent):
        result = self.client.post_actor_revise(uid, platform, user_agent)

        if uid not in self.actors:
            assert result == {"error": "Actor not found"}
        else:
            self.actors[uid] = {
                **self.actors[uid],
                "platform": platform,
                "user_agent": user_agent,
            }
            assert result == self.actors[uid]

    @rule(uid=IDS, actor=IDS, description=TEXT, tags=TEXT)
    def submit_instruction(self, uid, actor, description, tags):
        source = f"{uid}.png"
        result = self.client.put_instruction_submit(
            uid, source, actor, description, tags,
        )
        if actor not in self.actors:
            assert result == {"error": "Actor not found"}
        elif uid in self.instructions:
            assert result == {"error": "Identifier already exists"}
        else:
            record = {
                "uid": uid, "datetime": self.clock.return_value,
                "input": source, "actor": actor,
                "description": description, "tags": tags, "stage": "created",
            }
            assert result == record
            expected = {
                "uid": uid, "datetime": self.clock.return_value,
                "output": str(Path.cwd() / f"{uid}.jpg"),
                "stage": "done", "failure": "", "instruction": uid,
            }
            responses = self.client.get_response_show(uid)
            assert responses == [expected]
            self.instructions[uid] = {**record, "stage": "done"}
            self.responses[uid] = expected

    @rule(uid=IDS)
    def pop_instruction(self, uid):
        result = self.client.delete_instruction_pop(uid)

        if uid not in self.instructions:
            assert result == {"error": "Instruction not found"}
        else:
            assert result == {"deleted": uid}
            del self.instructions[uid]
            del self.responses[uid]
            assert self.client.get_response_show(uid) == []

    @rule(actor=IDS, uid=OPTIONAL_ID, stage=STAGES)
    def show_instruction(self, actor, uid, stage):
        expected = [
            item for item in self.instructions.values()
            if item["actor"] == actor
            and (uid is None or item["uid"] == uid)
            and (stage is None or item["stage"] == stage)
        ]

        assert self.client.get_instruction_show(
            actor,
            uid=uid,
            stage=stage,
        ) == expected

    @rule(uid=IDS, description=TEXT, tags=TEXT)
    def revise_instruction(self, uid, description, tags):
        result = self.client.post_instruction_revise(uid, description, tags)

        if uid not in self.instructions:
            assert result == {"error": "Instruction not found"}
        else:
            self.instructions[uid] = {
                **self.instructions[uid],
                "description": description,
                "tags": tags,
            }
            assert result == self.instructions[uid]

    @rule(instruction=IDS, stage=STAGES)
    def show_response(self, instruction, stage):
        expected = [
            item for item in self.responses.values()
            if item["instruction"] == instruction
            and (stage is None or item["stage"] == stage)
        ]

        assert self.client.get_response_show(
            instruction,
            stage=stage,
        ) == expected

    @rule()
    def show_report(self):
        cutoff = self.clock.return_value - REPORT_SECONDS
        expected = []

        for task in self.instructions.values():
            if task["datetime"] >= cutoff:
                response = self.responses[task["uid"]]
                expected.append({
                    "description": task["description"],
                    "output": response["output"],
                })

        assert self.client.get_report_show() == expected

    @rule(seconds=st.sampled_from([1, 359, 360, 361, 600]))
    def advance_time(self, seconds):
        self.clock.return_value += seconds

    @invariant()
    def records_match(self):
        assert self.client.get_actor_show() == list(self.actors.values())

        for actor in self.actors:
            assert self.client.get_instruction_show(actor) == [
                item for item in self.instructions.values()
                if item["actor"] == actor
            ]

        for uid, response in self.responses.items():
            assert self.client.get_response_show(uid) == [response]

        self.show_report()


TestApiStateMachine = ApiStateMachine.TestCase
TestApiStateMachine.settings = settings(
    max_examples=MAX_EXAMPLES,
    stateful_step_count=STATEFUL_STEPS,
    deadline=None,
    derandomize=True,
)


class TestApiWorkflow(unittest.TestCase):
    @settings(max_examples=35, deadline=None, derandomize=True)
    @given(method=METHODS, content_type=MEDIA_TYPES, accept=MEDIA_TYPES)
    def test_headers(self, method, content_type, accept):
        headers = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        if accept is not None:
            headers["Accept"] = accept
        expected = expected_status(method, content_type, accept)
        routes = {
            "GET": "/show/report", "DELETE": "/pop/actor/0",
            "PUT": "/submit/actor/0", "POST": "/revise/actor",
            "PATCH": "/revise/actor",
        }
        with running_api() as client:
            response = client.request(method, routes[method], headers=headers)
            assert response.status_code == expected
            assert response.headers["content-type"].startswith(JSON_TYPE)
            assert isinstance(response.json(), (list, dict))
            assert client.get_actor_show() == []

    @settings(max_examples=EXAMPLES, deadline=None, derandomize=True)
    @given(case=st.sampled_from([
        "bad_uid", "no_query", "bad_body", "extra_field", "line_break",
    ]))
    def test_validation(self, case):
        with running_api() as client:
            client.put_actor_submit(0, "Windows", "agent")
            if case == "bad_uid":
                response = client.request("DELETE", "/pop/actor/text")
            elif case == "no_query":
                response = client.request("PUT", "/submit/actor/1")
            elif case == "bad_body":
                response = client.request("POST", "/revise/actor", json=[])
            elif case == "extra_field":
                response = client.request("POST", "/revise/instruction", json={
                    "uid": 0, "description": "x", "tags": "x", "stage": "x",
                })
            else:
                result = client.put_instruction_submit(0, "a\nb.png", 0)
                assert result == {
                    "error": "Input path must not contain line breaks",
                }
                return
            assert response.status_code == OK
            assert response.json() == {"error": "Invalid request parameters"}

    @settings(max_examples=6, deadline=None, derandomize=True)
    @given(mode=st.sampled_from(["RGB", "RGBA", "L", "P"]))
    def test_real_conversion(self, mode):
        with tempfile.TemporaryDirectory(prefix="png jpeg ") as folder:
            source = Path(folder) / "пример файла.png"
            Image.new(mode, IMAGE_SIZE).save(source)
            with running_api(test_mode=False) as client:
                client.put_actor_submit(0, "Windows", "agent")
                created = client.put_instruction_submit(0, str(source), 0)
                assert created["stage"] == "created"
                result = client.get_response_show(0)[0]
                assert result["stage"] == "done"
                assert result["failure"] == ""
                expected_path = Path(folder) / "пример файла.jpg"
                assert result["output"] == str(expected_path)
                with Image.open(result["output"]) as image:
                    assert image.format == "JPEG"
                    assert image.mode == "RGB"
                    assert image.size == IMAGE_SIZE
                assert client.get_instruction_show(0)[0]["stage"] == "done"

    @settings(max_examples=EXAMPLES, deadline=None, derandomize=True)
    @given(case=st.sampled_from(["missing", "broken"]))
    def test_conversion_failure(self, case):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.png"
            target = Path(folder) / "input.jpg"
            if case == "broken":
                source.write_text("not an image", encoding="utf-8")
            with running_api(test_mode=False) as client:
                client.put_actor_submit(0, "Windows", "agent")
                client.put_instruction_submit(0, str(source), 0)
                result = client.get_response_show(0)[0]
                assert result["stage"] == "failed"
                assert result["output"] == ""
                assert result["failure"]
                assert not target.exists()
                assert client.get_instruction_show(0)[0]["stage"] == "failed"
                client.delete_instruction_pop(0)
                assert client.get_response_show(0) == []

    @settings(max_examples=4, deadline=None, derandomize=True)
    @given(uid=st.integers(min_value=0, max_value=2))
    def test_test_mode(self, uid):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.png"
            target = Path(folder) / "input.jpg"
            with running_api(test_mode=True) as client:
                client.put_actor_submit(0, "Windows", "agent")
                client.put_instruction_submit(uid, str(source), 0)
                result = client.get_response_show(uid)[0]
                assert result["stage"] == "done"
                assert result["output"] == str(target)
                assert result["failure"] == ""
                assert not target.exists()
                assert client.get_instruction_show(0)[0]["stage"] == "done"
                client.delete_instruction_pop(uid)
                assert client.get_response_show(uid) == []

    @settings(max_examples=4, deadline=None, derandomize=True)
    @given(uid=st.integers(min_value=0, max_value=2))
    def test_deletion(self, uid):
        with running_api() as client:
            client.put_actor_submit(uid, "Windows", "agent")
            client.put_actor_submit(uid + 1, "Windows", "agent")
            client.put_instruction_submit(uid, "first.png", uid)
            client.put_instruction_submit(uid + 1, "second.png", uid + 1)
            assert client.delete_actor_pop(uid) == {
                "error": "Actor has instructions",
            }
            assert client.delete_instruction_pop(uid) == {"deleted": uid}
            assert client.get_response_show(uid) == []
            assert len(client.get_response_show(uid + 1)) == 1
            assert client.delete_actor_pop(uid) == {"deleted": uid}
            assert client.get_actor_show(uid=uid) == []

    @settings(max_examples=6, deadline=None, derandomize=True)
    @given(offset=st.sampled_from([0, 359, 360, 361, 600]))
    def test_report_boundary(self, offset):
        with patch(
            "first_step.get_current_time", return_value=INITIAL_TIME,
        ) as clock:
            with running_api() as client:
                client.put_actor_submit(0, "Windows", "agent")
                client.put_instruction_submit(0, "input.png", 0, "example")
                response = client.get_response_show(0)[0]
                clock.return_value = INITIAL_TIME + offset
                expected = []
                if offset <= REPORT_SECONDS:
                    expected = [{
                        "description": "example", "output": response["output"],
                    }]
                assert client.get_report_show() == expected

    @settings(max_examples=6, deadline=None, derandomize=True)
    @given(error=st.sampled_from(["os_error", "timeout"]))
    def test_launch_errors(self, error):
        failure = OSError("Cannot start the converter")
        if error == "timeout":
            failure = subprocess.TimeoutExpired("converter.py", 60)
        with patch("api.run_converter", side_effect=failure):
            with running_api(test_mode=False) as client:
                client.put_actor_submit(0, "Windows", "agent")
                client.put_instruction_submit(0, "input.png", 0)
                result = client.get_response_show(0)[0]
                assert result["stage"] == "failed"
                assert result["failure"]
                assert client.get_report_show() == [{
                    "description": "PNG to JPEG", "output": "",
                }]

    @settings(max_examples=4, deadline=None, derandomize=True)
    @given(uid=st.integers(min_value=0, max_value=2))
    def test_unfinished_instruction(self, uid):
        with patch("api.convert_instruction", new_callable=AsyncMock):
            with running_api() as client:
                client.put_actor_submit(0, "Windows", "agent")
                result = client.put_instruction_submit(uid, "input.png", 0)
                assert result["stage"] == "created"
                assert client.get_instruction_show(0)[0]["stage"] == "created"
                assert client.get_response_show(uid) == []
                assert client.get_report_show() == []
                assert client.delete_instruction_pop(uid) == {
                    "error": "Instruction is still running",
                }
                updated = client.post_instruction_revise(uid, "new", "tag")
                assert updated["description"] == "new"


if __name__ == "__main__":
    unittest.main()
