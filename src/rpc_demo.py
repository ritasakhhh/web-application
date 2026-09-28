from rpc_client import RpcClient


def demo_actor(client):
    actor = client.create_actor(
        "Windows",
        "Chrome",
    )
    actor_id = actor[0]

    print("create_actor:", actor)
    print("get_actors:", client.get_actors())
    print(
        "update_actor:",
        client.update_actor(
            actor_id,
            "Linux",
            "Firefox",
        ),
    )

    return actor_id


def demo_instruction(client, actor_id):
    instruction = client.create_instruction(
        "Hello",
        actor_id,
        "Test instruction",
        "test",
        "new",
    )
    instruction_id = instruction[0]

    print("create_instruction:", instruction)
    print("get_instructions:", client.get_instructions())
    print(
        "update_instruction:",
        client.update_instruction(
            instruction_id,
            "Hello updated",
            actor_id,
            "Updated instruction",
            "python",
            "running",
        ),
    )

    return instruction_id


def demo_response(client, instruction_id):
    response = client.create_response(
        "Success",
        "done",
        "",
        instruction_id,
    )
    response_id = response[0]

    print("create_response:", response)
    print("get_responses:", client.get_responses())
    print(
        "update_response:",
        client.update_response(
            response_id,
            "Updated success",
            "completed",
            "",
            instruction_id,
        ),
    )

    return response_id


def main():
    client = RpcClient()

    actor_id = demo_actor(client)
    instruction_id = demo_instruction(client, actor_id)
    response_id = demo_response(client, instruction_id)

    print(
        "get_recent_responses:",
        client.get_recent_responses(),
    )

    print("delete_response:", client.delete_response(response_id))
    print(
        "delete_instruction:",
        client.delete_instruction(instruction_id),
    )
    print("delete_actor:", client.delete_actor(actor_id))

    try:
        client.delete_actor(999)
    except ValueError as error:
        print("RPC error:", error)


if __name__ == "__main__":
    main()