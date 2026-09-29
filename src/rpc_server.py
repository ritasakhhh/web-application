import socket
from xmlrpc.client import Fault, dumps, loads

import first_step
from rpc_protocol import (
    HOST,
    OPERATIONS,
    PORT,
    PROTOCOL_VERSION,
    REQUEST_HEADER_SIZE,
    receive_exact,
)

FUNCTIONS = {
    OPERATIONS["create_actor"]: first_step.create_actor,
    OPERATIONS["delete_actor"]: first_step.delete_actor,
    OPERATIONS["get_actors"]: first_step.get_actors,
    OPERATIONS["update_actor"]: first_step.update_actor,
    OPERATIONS["create_instruction"]: first_step.create_instruction,
    OPERATIONS["delete_instruction"]: first_step.delete_instruction,
    OPERATIONS["get_instructions"]: first_step.get_instructions,
    OPERATIONS["update_instruction"]: first_step.update_instruction,
    OPERATIONS["create_response"]: first_step.create_response,
    OPERATIONS["delete_response"]: first_step.delete_response,
    OPERATIONS["get_responses"]: first_step.get_responses,
    OPERATIONS["update_response"]: first_step.update_response,
    OPERATIONS["get_recent_responses"]: first_step.get_recent_responses,
}


def make_response_body(result=None, error=None):
    if error is not None:
        xml = dumps(
            Fault(1, str(error)),
            allow_none=True,
        )
    else:
        xml = dumps(
            (result,),
            methodresponse=True,
            allow_none=True,
        )

    return xml.encode("utf-8")


def log_request(operation, body):
    print("REQUEST")
    print(f"operation: {operation}")
    print(f"body size: {len(body)}")
    print(body.decode("utf-8"))


def log_response(operation, body):
    print("RESPONSE")
    print(f"version: {PROTOCOL_VERSION}")
    print(f"operation: {operation}")
    print(f"body size: {len(body)}")
    print(body.decode("utf-8"))


def handle_client(connection):
    header = receive_exact(
        connection,
        REQUEST_HEADER_SIZE,
    )

    body_size = int.from_bytes(header[:3], "big")
    operation = header[3]
    body = receive_exact(connection, body_size)

    log_request(operation, body)

    try:
        params, _ = loads(body)
        function = FUNCTIONS.get(operation)

        if function is None:
            raise ValueError("Unknown operation")

        result = function(*params)
        response_body = make_response_body(result=result)
    except Exception as error:
        response_body = make_response_body(error=error)

    response_header = (
            bytes([PROTOCOL_VERSION, operation])
            + len(response_body).to_bytes(4, "big")
    )

    log_response(operation, response_body)
    connection.sendall(response_header + response_body)


def main():
    with socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
    ) as server:
        server.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )
        server.bind((HOST, PORT))
        server.listen()

        print("RPC server started on {}:{}".format(HOST, PORT))

        while True:
            connection, address = server.accept()
            print(f"Client connected: {address}")

            with connection:
                handle_client(connection)


if __name__ == "__main__":
    main()
