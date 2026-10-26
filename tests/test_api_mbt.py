from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from hypothesis import settings, strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    rule,
)

from http_support import running_api, wait_until

INITIAL_TIME = 1_700_000_000
REPORT_SECONDS = 360
MAX_EXAMPLES = 20
STATEFUL_STEPS = 25

IDS = st.integers(min_value=0, max_value=4)
OPTIONAL_ID = st.one_of(st.none(), IDS)
TEXT = st.text(alphabet="abc XYZ012_абв", min_size=0, max_size=10)
OPTIONAL_TEXT = st.one_of(st.none(), TEXT)
STAGES = st.sampled_from([None, "created", "running", "done", "failed"])


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
            responses = wait_until(lambda: self.client.get_response_show(uid))
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
