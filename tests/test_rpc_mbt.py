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

        self.client = rpc_client.RPCClient()
        self.actors = {}
        self.instructions = {}
        self.responses = {}

    def prepare_actor(self):
        actor = self.client.create_actor("base", "agent")
        actor_id = actor[0]

        self.actors[actor_id] = [
            actor_id,
            actor[1],
            "base",
            "agent",
        ]

        updated = self.client.update_actor(
            actor_id,
            "updated",
            "browser",
        )
        self.actors[actor_id] = updated

        temporary = self.client.create_actor("temp", "temp")
        self.client.delete_actor(temporary[0])

        return actor_id

    def prepare_instruction(self, actor_id):
        instruction = self.client.create_instruction(
            "input",
            actor_id,
            "description",
            "tags",
            "new",
        )
        instruction_id = instruction[0]

        updated = self.client.update_instruction(
            instruction_id,
            "updated",
            actor_id,
            "updated_description",
            "updated_tags",
            "running",
        )
        self.instructions[instruction_id] = updated

        temporary = self.client.create_instruction(
            "temp",
            actor_id,
            "temp",
            "temp",
            "temp",
        )
        self.client.delete_instruction(temporary[0])

        return instruction_id

    def prepare_response(self, instruction_id):
        response = self.client.create_response(
            "output",
            "done",
            "",
            instruction_id,
        )
        response_id = response[0]

        updated = self.client.update_response(
            response_id,
            "updated_output",
            "completed",
            "",
            instruction_id,
        )
        self.responses[response_id] = updated

        temporary = self.client.create_response(
            "temp",
            "temp",
            "",
            instruction_id,
        )
        self.client.delete_response(temporary[0])

    @initialize()
    def initialize_data(self):
        actor_id = self.prepare_actor()
        instruction_id = self.prepare_instruction(actor_id)
        self.prepare_response(instruction_id)
        self.check_model()

    @rule(platform=TEXT, user_agent=TEXT)
    def create_actor(self, platform, user_agent):
        expected_id = get_next_id(self.actors)
        actor = self.client.create_actor(platform, user_agent)

        assert actor[0] == expected_id
        assert actor[2:] == [platform, user_agent]

        self.actors[expected_id] = actor

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

        result = self.client.update_actor(
            actor_id,
            platform,
            user_agent,
        )

        assert result == expected
        self.actors[actor_id] = expected

    @precondition(lambda self: bool(self.actors))
    @rule()
    def delete_actor(self):
        actor_id = next(iter(self.actors))

        assert self.client.delete_actor(actor_id) is True
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

        instruction = self.client.create_instruction(
            input_text,
            actor_id,
            description,
            tags,
            stage,
        )

        assert instruction[0] == expected_id
        self.instructions[expected_id] = instruction

    @precondition(
        lambda self: bool(self.instructions) and bool(self.actors)
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

        result = self.client.update_instruction(
            instruction_id,
            input_text,
            actor_id,
            description,
            tags,
            stage,
        )

        assert result == expected
        self.instructions[instruction_id] = expected

    @precondition(lambda self: bool(self.instructions))
    @rule()
    def delete_instruction(self):
        instruction_id = next(iter(self.instructions))

        assert self.client.delete_instruction(instruction_id) is True
        del self.instructions[instruction_id]

    @precondition(lambda self: bool(self.instructions))
    @rule(output=TEXT, stage=TEXT, failure=TEXT)
    def create_response(self, output, stage, failure):
        instruction_id = next(iter(self.instructions))
        expected_id = get_next_id(self.responses)

        response = self.client.create_response(
            output,
            stage,
            failure,
            instruction_id,
        )

        assert response[0] == expected_id
        self.responses[expected_id] = response

    @precondition(
        lambda self: bool(self.responses)
                     and bool(self.instructions)
    )
    @rule(output=TEXT, stage=TEXT, failure=TEXT)
    def update_response(self, output, stage, failure):
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

        result = self.client.update_response(
            response_id,
            output,
            stage,
            failure,
            instruction_id,
        )

        assert result == expected
        self.responses[response_id] = expected

    @precondition(lambda self: bool(self.responses))
    @rule()
    def delete_response(self):
        response_id = next(iter(self.responses))

        assert self.client.delete_response(response_id) is True
        del self.responses[response_id]

    def get_recent_model(self):
        current_time = int(time.time())
        result = []

        for instruction in self.instructions.values():
            if instruction[1] >= current_time - SIX_MINUTES:
                for response in self.responses.values():
                    if instruction[0] == response[5]:
                        result.append(
                            [instruction[4], response[2]]
                        )

        return result

    def check_model(self):
        assert self.client.get_actors() == list(
            self.actors.values()
        )
        assert self.client.get_instructions() == list(
            self.instructions.values()
        )
        assert self.client.get_responses() == list(
            self.responses.values()
        )
        assert (
                self.client.get_recent_responses()
                == self.get_recent_model()
        )

    @invariant()
    def model_matches_rpc(self):
        self.check_model()


class TestRpcStateMachine(RpcStateMachine.TestCase):
    @classmethod
    def setUpClass(cls):
        server_thread = threading.Thread(
            target=rpc_server.main,
            daemon=True,
        )
        server_thread.start()
        time.sleep(SERVER_START_DELAY)


TestRpcStateMachine.settings = settings(
    max_examples=10,
    stateful_step_count=10,
    deadline=None,
)
