import threading
import time

from hypothesis import settings, strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    precondition,
    rule,
)

import first_step
import rpc_client
import rpc_server

TEST_PORT = 5001
SERVER_START_DELAY = 0.5
SIX_MINUTES = 6 * 60

TEXT = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
    min_size=1,
    max_size=12,
)

rpc_client.PORT = TEST_PORT
rpc_server.PORT = TEST_PORT


def get_next_id(records):
    if not records:
        return 0
    return max(records) + 1


class RpcStateMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()

        first_step.actors.clear()
        first_step.instructions.clear()
        first_step.responses.clear()

        self.client = rpc_client.RpcClient()

        self.actors = {}
        self.instructions = {}
        self.responses = {}

        self.last_action = "initialize"

    def rpc_call(self, name, *args):
        self.last_action = name
        method = getattr(self.client, name)

        try:
            return method(*args)
        except Exception as error:
            message = f"{name}: RPC call failed: {error}"
            raise AssertionError(message) from error

    def assert_result(self, name, result, expected):
        if result != expected:
            message = (
                f"{name}: expected {expected}, "
                f"got {result}"
            )
            raise AssertionError(message)

    @initialize()
    def initialize_data(self):
        actor = self.rpc_call(
            "create_actor",
            "base",
            "agent",
        )
        self.actors[actor[0]] = actor

        instruction = self.rpc_call(
            "create_instruction",
            "input",
            actor[0],
            "description",
            "tags",
            "new",
        )
        self.instructions[instruction[0]] = instruction

        response = self.rpc_call(
            "create_response",
            "output",
            "done",
            "",
            instruction[0],
        )
        self.responses[response[0]] = response

    @rule(platform=TEXT, user_agent=TEXT)
    def create_actor(self, platform, user_agent):
        expected_id = get_next_id(self.actors)

        actor = self.rpc_call(
            "create_actor",
            platform,
            user_agent,
        )

        self.assert_result(
            "create_actor",
            actor[0],
            expected_id,
        )
        self.assert_result(
            "create_actor",
            actor[2:],
            [platform, user_agent],
        )

        self.actors[actor[0]] = actor

    @rule()
    def get_actors(self):
        result = self.rpc_call("get_actors")
        expected = list(self.actors.values())

        self.assert_result(
            "get_actors",
            result,
            expected,
        )

    @precondition(lambda self: bool(self.actors))
    @rule(platform=TEXT, user_agent=TEXT)
    def update_actor(self, platform, user_agent):
        actor_id = next(iter(self.actors))
        old_actor = self.actors[actor_id]

        expected = [
            actor_id,
            old_actor[1],
            platform,
            user_agent,
        ]

        result = self.rpc_call(
            "update_actor",
            actor_id,
            platform,
            user_agent,
        )

        self.assert_result(
            "update_actor",
            result,
            expected,
        )
        self.actors[actor_id] = expected

    @precondition(lambda self: bool(self.actors))
    @rule()
    def delete_actor(self):
        actor_id = next(iter(self.actors))

        result = self.rpc_call(
            "delete_actor",
            actor_id,
        )

        self.assert_result(
            "delete_actor",
            result,
            True,
        )
        del self.actors[actor_id]

    @precondition(lambda self: bool(self.actors))
    @rule(
        input_text=TEXT,
        description=TEXT,
        tags=TEXT,
        stage=TEXT,
    )
    def create_instruction(
            self,
            input_text,
            description,
            tags,
            stage,
    ):
        actor_id = next(iter(self.actors))
        expected_id = get_next_id(self.instructions)

        result = self.rpc_call(
            "create_instruction",
            input_text,
            actor_id,
            description,
            tags,
            stage,
        )

        expected = [
            expected_id,
            result[1],
            input_text,
            actor_id,
            description,
            tags,
            stage,
        ]

        self.assert_result(
            "create_instruction",
            result,
            expected,
        )
        self.instructions[expected_id] = result

    @rule()
    def get_instructions(self):
        result = self.rpc_call("get_instructions")
        expected = list(self.instructions.values())

        self.assert_result(
            "get_instructions",
            result,
            expected,
        )

    @precondition(
        lambda self: (
                bool(self.instructions)
                and bool(self.actors)
        )
    )
    @rule(
        input_text=TEXT,
        description=TEXT,
        tags=TEXT,
        stage=TEXT,
    )
    def update_instruction(
            self,
            input_text,
            description,
            tags,
            stage,
    ):
        instruction_id = next(iter(self.instructions))
        actor_id = next(iter(self.actors))
        old_instruction = self.instructions[instruction_id]

        expected = [
            instruction_id,
            old_instruction[1],
            input_text,
            actor_id,
            description,
            tags,
            stage,
        ]

        result = self.rpc_call(
            "update_instruction",
            instruction_id,
            input_text,
            actor_id,
            description,
            tags,
            stage,
        )

        self.assert_result(
            "update_instruction",
            result,
            expected,
        )
        self.instructions[instruction_id] = expected

    @precondition(lambda self: bool(self.instructions))
    @rule()
    def delete_instruction(self):
        instruction_id = next(iter(self.instructions))

        result = self.rpc_call(
            "delete_instruction",
            instruction_id,
        )

        self.assert_result(
            "delete_instruction",
            result,
            True,
        )
        del self.instructions[instruction_id]

    @precondition(lambda self: bool(self.instructions))
    @rule(
        output=TEXT,
        stage=TEXT,
        failure=TEXT,
    )
    def create_response(
            self,
            output,
            stage,
            failure,
    ):
        instruction_id = next(iter(self.instructions))
        expected_id = get_next_id(self.responses)

        result = self.rpc_call(
            "create_response",
            output,
            stage,
            failure,
            instruction_id,
        )

        expected = [
            expected_id,
            result[1],
            output,
            stage,
            failure,
            instruction_id,
        ]

        self.assert_result(
            "create_response",
            result,
            expected,
        )
        self.responses[expected_id] = result

    @rule()
    def get_responses(self):
        result = self.rpc_call("get_responses")
        expected = list(self.responses.values())

        self.assert_result(
            "get_responses",
            result,
            expected,
        )

    @precondition(
        lambda self: (
                bool(self.responses)
                and bool(self.instructions)
        )
    )
    @rule(
        output=TEXT,
        stage=TEXT,
        failure=TEXT,
    )
    def update_response(
            self,
            output,
            stage,
            failure,
    ):
        response_id = next(iter(self.responses))
        instruction_id = next(iter(self.instructions))
        old_response = self.responses[response_id]

        expected = [
            response_id,
            old_response[1],
            output,
            stage,
            failure,
            instruction_id,
        ]

        result = self.rpc_call(
            "update_response",
            response_id,
            output,
            stage,
            failure,
            instruction_id,
        )

        self.assert_result(
            "update_response",
            result,
            expected,
        )
        self.responses[response_id] = expected

    @precondition(lambda self: bool(self.responses))
    @rule()
    def delete_response(self):
        response_id = next(iter(self.responses))

        result = self.rpc_call(
            "delete_response",
            response_id,
        )

        self.assert_result(
            "delete_response",
            result,
            True,
        )
        del self.responses[response_id]

    @rule()
    def get_recent_responses(self):
        result = self.rpc_call(
            "get_recent_responses"
        )
        expected = self.get_recent_model()

        self.assert_result(
            "get_recent_responses",
            result,
            expected,
        )

    def get_recent_model(self):
        current_time = int(time.time())
        result = []

        for instruction in self.instructions.values():
            is_recent = (
                    instruction[1]
                    >= current_time - SIX_MINUTES
            )

            if is_recent:
                for response in self.responses.values():
                    if instruction[0] == response[5]:
                        result.append(
                            [
                                instruction[4],
                                response[2],
                            ]
                        )

        return result

    def check_model(self):
        action = self.last_action

        actors = self.rpc_call("get_actors")
        instructions = self.rpc_call("get_instructions")
        responses = self.rpc_call("get_responses")
        recent = self.rpc_call("get_recent_responses")

        self.last_action = action

        expected_actors = list(self.actors.values())
        expected_instructions = list(
            self.instructions.values()
        )
        expected_responses = list(
            self.responses.values()
        )
        expected_recent = self.get_recent_model()

        if actors != expected_actors:
            raise AssertionError(
                f"{action}: Actor model mismatch"
            )

        if instructions != expected_instructions:
            raise AssertionError(
                f"{action}: Instruction model mismatch"
            )

        if responses != expected_responses:
            raise AssertionError(
                f"{action}: Response model mismatch"
            )

        if recent != expected_recent:
            raise AssertionError(
                f"{action}: recent responses mismatch"
            )

    @invariant()
    def model_matches_rpc(self):
        self.check_model()


def start_test_server():
    server_thread = threading.Thread(
        target=rpc_server.main,
        daemon=True,
    )
    server_thread.start()

    time.sleep(SERVER_START_DELAY)


start_test_server()


class TestRpcStateMachine(RpcStateMachine.TestCase):
    pass


TestRpcStateMachine.settings = settings(
    max_examples=20,
    stateful_step_count=25,
    deadline=None,
)
