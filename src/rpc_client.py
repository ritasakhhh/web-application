import socket
from xmlrpc.client import Fault, dumps, loads

from rpc_protocol import (
    HOST,
    OPERATIONS,
    PORT,
    PROTOCOL_VERSION,
    RESPONSE_HEADER_SIZE,
    receive_exact,
)


class RpcClient:
    def _call(self, name, *args):
        operation = OPERATIONS[name]
        request_body = dumps(
            args,
            allow_none=True,
        ).encode("utf-8")

        request_header = (
                len(request_body).to_bytes(3, "big")
                + bytes([operation])
        )

        with socket.create_connection((HOST, PORT)) as sock:
            sock.sendall(request_header + request_body)

            response_header = receive_exact(
                sock,
                RESPONSE_HEADER_SIZE,
            )

            version = response_header[0]
            response_operation = response_header[1]
            body_size = int.from_bytes(
                response_header[2:6],
                "big",
            )
            response_body = receive_exact(sock, body_size)

        if version != PROTOCOL_VERSION:
            raise ValueError("Wrong protocol version")

        if response_operation != operation:
            raise ValueError("Wrong operation code")

        try:
            values, _ = loads(response_body)
        except Fault as error:
            raise ValueError(error.faultString) from error

        return values[0]

    def create_actor(self, platform, user_agent):
        return self._call(
            "create_actor",
            platform,
            user_agent,
        )

    def delete_actor(self, uid):
        return self._call("delete_actor", uid)

    def get_actors(self):
        return self._call("get_actors")

    def update_actor(self, uid, platform, user_agent):
        return self._call(
            "update_actor",
            uid,
            platform,
            user_agent,
        )

    def create_instruction(
            self,
            input_text,
            actor_id,
            description,
            tags,
            stage,
    ):
        return self._call(
            "create_instruction",
            input_text,
            actor_id,
            description,
            tags,
            stage,
        )

    def delete_instruction(self, uid):
        return self._call("delete_instruction", uid)

    def get_instructions(self):
        return self._call("get_instructions")

    def update_instruction(
            self,
            uid,
            input_text,
            actor_id,
            description,
            tags,
            stage,
    ):
        return self._call(
            "update_instruction",
            uid,
            input_text,
            actor_id,
            description,
            tags,
            stage,
        )

    def create_response(
            self,
            output,
            stage,
            failure,
            instruction_id,
    ):
        return self._call(
            "create_response",
            output,
            stage,
            failure,
            instruction_id,
        )

    def delete_response(self, uid):
        return self._call("delete_response", uid)

    def get_responses(self):
        return self._call("get_responses")

    def update_response(
            self,
            uid,
            output,
            stage,
            failure,
            instruction_id,
    ):
        return self._call(
            "update_response",
            uid,
            output,
            stage,
            failure,
            instruction_id,
        )

    def get_recent_responses(self):
        return self._call("get_recent_responses")
