HOST = "127.0.0.1"
PORT = 5000
PROTOCOL_VERSION = 1

REQUEST_HEADER_SIZE = 4
RESPONSE_HEADER_SIZE = 6

OPERATIONS = {
    "create_actor": 1,
    "delete_actor": 2,
    "get_actors": 3,
    "update_actor": 4,
    "create_instruction": 5,
    "delete_instruction": 6,
    "get_instructions": 7,
    "update_instruction": 8,
    "create_response": 9,
    "delete_response": 10,
    "get_responses": 11,
    "update_response": 12,
    "get_recent_responses": 13,
}


def receive_exact(sock, size):
    data = b""

    while len(data) < size:
        part = sock.recv(size - len(data))

        if not part:
            raise ConnectionError("Connection closed")

        data += part

    return data
