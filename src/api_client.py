import httpx

PREFIX = "/private/api/v2"
DEFAULT_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 10

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}


class ApiClient:
    def __init__(self, base_url=DEFAULT_URL, session=None):
        self.base_url = base_url.rstrip("/")
        if session is None:
            session = httpx.Client(
                timeout=REQUEST_TIMEOUT,
                trust_env=False,
            )
        self.session = session

    def close(self):
        self.session.close()

    def request(
            self,
            method,
            path,
            params=None,
            json=None,
            headers=None,
    ):
        params = {
            key: value for key, value in (params or {}).items()
            if value is not None
        }

        return self.session.request(
            method,
            self.base_url + PREFIX + path,
            params=params,
            json=json,
            headers=HEADERS if headers is None else headers,
        )

    def _call(self, method, path, params=None, json=None):
        response = self.request(
            method,
            path,
            params=params,
            json=json,
        )

        response.raise_for_status()

        return response.json()

    def put_actor_submit(self, uid, platform, user_agent):
        return self._call(
            "PUT",
            f"/submit/actor/{uid}",
            params={
                "platform": platform,
                "user_agent": user_agent,
            },
        )

    def delete_actor_pop(self, uid):
        return self._call(
            "DELETE",
            f"/pop/actor/{uid}",
        )

    def get_actor_show(self, **filters):
        return self._call(
            "GET",
            "/show/actor",
            params=filters,
        )

    def post_actor_revise(self, uid, platform, user_agent):
        return self._call(
            "POST",
            "/revise/actor",
            json={
                "uid": uid,
                "platform": platform,
                "user_agent": user_agent,
            },
        )

    def put_instruction_submit(
            self,
            uid,
            input_path,
            actor,
            description="PNG to JPEG",
            tags="png,jpeg",
    ):
        return self._call(
            "PUT",
            f"/submit/instruction/{uid}",
            params={
                "input": input_path,
                "actor": actor,
                "description": description,
                "tags": tags,
            },
        )

    def delete_instruction_pop(self, uid):
        return self._call(
            "DELETE",
            f"/pop/instruction/{uid}",
        )

    def get_instruction_show(self, actor, **filters):
        return self._call(
            "GET",
            f"/show/instruction/{actor}",
            params=filters,
        )

    def post_instruction_revise(self, uid, description, tags):
        return self._call(
            "POST",
            "/revise/instruction",
            json={
                "uid": uid,
                "description": description,
                "tags": tags,
            },
        )

    def get_response_show(self, instruction, **filters):
        return self._call(
            "GET",
            f"/show/response/{instruction}",
            params=filters,
        )

    def get_report_show(self):
        return self._call(
            "GET",
            "/show/report",
        )
