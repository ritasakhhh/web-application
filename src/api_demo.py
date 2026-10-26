import time

from api_client import ApiClient

POLL_INTERVAL = 0.2
WAIT_TIMEOUT = 70


def wait_for_response(client, uid):
    deadline = time.monotonic() + WAIT_TIMEOUT

    while time.monotonic() < deadline:
        responses = client.get_response_show(uid)

        if responses:
            return responses[0]

        time.sleep(POLL_INTERVAL)

    raise TimeoutError("Conversion did not finish in time")


def main():
    client = ApiClient()

    try:
        uid = int(input("New instruction ID: "))
        source = input("PNG file: ")

        actors = client.get_actor_show(uid=0)

        if not actors:
            print(client.put_actor_submit(0, "Windows", "api_demo"))

        instruction = client.put_instruction_submit(uid, source, 0)
        print(instruction)

        if "error" in instruction:
            return

        print(wait_for_response(client, uid))
        print(client.get_report_show())

    finally:
        client.close()


if __name__ == "__main__":
    main()
