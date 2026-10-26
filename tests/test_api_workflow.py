from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from hypothesis import given, settings, strategies as st
from PIL import Image

from http_support import running_api, wait_until

OK = 200
METHOD_NOT_ALLOWED = 405
UNSUPPORTED_MEDIA_TYPE = 415
NOT_ACCEPTABLE = 406
NOW = 1_700_000_000
REPORT_SECONDS = 360
JSON_TYPE = "application/json"
EXAMPLES = 12
IMAGE_SIZE = (12, 8)
METHODS = st.sampled_from(["GET", "DELETE", "POST", "PUT", "PATCH"])
MEDIA_TYPES = st.sampled_from([None, JSON_TYPE, "text/plain"])


class TestApiWorkflow(unittest.TestCase):
    @settings(max_examples=35, deadline=None, derandomize=True)
    @given(method=METHODS, content_type=MEDIA_TYPES, accept=MEDIA_TYPES)
    def test_headers(self, method, content_type, accept):
        headers = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        if accept is not None:
            headers["Accept"] = accept
        if method in {"POST", "PUT", "PATCH"} and content_type != JSON_TYPE:
            expected = UNSUPPORTED_MEDIA_TYPE
        elif accept != JSON_TYPE:
            expected = NOT_ACCEPTABLE
        elif method in {"GET", "DELETE", "POST", "PUT"}:
            expected = OK
        else:
            expected = METHOD_NOT_ALLOWED
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
                result = wait_until(lambda: client.get_response_show(0))[0]
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
    @given(case=st.sampled_from(["missing", "broken", "test_mode"]))
    def test_conversion_failure_and_test_mode(self, case):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.png"
            target = Path(folder) / "input.jpg"
            if case == "broken":
                source.write_text("not an image", encoding="utf-8")
            with running_api(test_mode=case == "test_mode") as client:
                client.put_actor_submit(0, "Windows", "agent")
                client.put_instruction_submit(0, str(source), 0)
                result = wait_until(lambda: client.get_response_show(0))[0]
                if case == "test_mode":
                    assert result["stage"] == "done"
                    assert result["output"] == str(target)
                    assert result["failure"] == ""
                else:
                    assert result["stage"] == "failed"
                    assert result["output"] == ""
                    assert result["failure"]
                assert not target.exists()
                assert client.get_instruction_show(0)[0]["stage"] == (
                    result["stage"]
                )
                client.delete_instruction_pop(0)
                assert client.get_response_show(0) == []

    @settings(max_examples=6, deadline=None, derandomize=True)
    @given(offset=st.sampled_from([0, 359, 360, 361, 600]))
    def test_report_boundary(self, offset):
        with patch("first_step.get_current_time", return_value=NOW) as clock:
            with running_api() as client:
                client.put_actor_submit(0, "Windows", "agent")
                client.put_instruction_submit(0, "input.png", 0, "example")
                response = wait_until(lambda: client.get_response_show(0))[0]
                clock.return_value = NOW + offset
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
                result = wait_until(lambda: client.get_response_show(0))[0]
                assert result["stage"] == "failed"
                assert result["failure"]
                assert client.get_report_show() == [{
                    "description": "PNG to JPEG", "output": "",
                }]

    @settings(max_examples=4, deadline=None, derandomize=True)
    @given(uid=st.integers(min_value=0, max_value=2))
    def test_server_remains_responsive(self, uid):
        started = threading.Event()
        release = threading.Event()

        def controlled_conversion(input_path, output_path):
            started.set()
            assert release.wait(timeout=10)

        with patch("api.run_converter", side_effect=controlled_conversion):
            with running_api(test_mode=False) as client:
                try:
                    client.put_actor_submit(0, "Windows", "agent")
                    result = client.put_instruction_submit(uid, "input.png", 0)
                    assert result["stage"] == "created"
                    wait_until(started.is_set)
                    tasks = client.get_instruction_show(0)
                    assert tasks[0]["stage"] == "running"
                    assert client.get_response_show(uid) == []
                    assert client.get_report_show() == []
                    assert client.delete_instruction_pop(uid) == {
                        "error": "Instruction is still running",
                    }
                    assert client.post_instruction_revise(uid, "new", "tag")[
                               "description"
                           ] == "new"
                finally:
                    release.set()
                assert wait_until(lambda: client.get_response_show(uid))


if __name__ == "__main__":
    unittest.main()
