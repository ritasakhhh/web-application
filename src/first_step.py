import datetime

SIX_MINUTES = 6 * 60

actors = []
instructions = []
responses = []


def get_current_time() -> int:
    return int(datetime.datetime.now().timestamp())


def get_next_id(table: list) -> int:
    if len(table) == 0:
        return 0

    return max(entity[0] for entity in table) + 1


def has_id(table: list, uid: int) -> bool:
    for entity in table:
        if entity[0] == uid:
            return True

    return False


def create_actor(
        platform: str,
        user_agent: str,
) -> tuple:
    actor = (
        get_next_id(actors),
        get_current_time(),
        platform,
        user_agent,
    )

    actors.append(actor)
    return actor


def get_actors() -> list:
    return actors


def delete_actor(uid: int) -> bool:
    for actor in actors:
        if actor[0] == uid:
            actors.remove(actor)
            return True

    raise ValueError("Actor not found")


def update_actor(
        uid: int,
        platform: str,
        user_agent: str,
) -> tuple:
    for index, actor in enumerate(actors):
        if actor[0] == uid:
            updated_actor = (
                actor[0],
                actor[1],
                platform,
                user_agent,
            )

            actors[index] = updated_actor
            return updated_actor

    raise ValueError("Actor not found")


def create_instruction(
        input_text: str,
        actor_id: int,
        description: str,
        tags: str,
        stage: str,
) -> tuple:
    if not has_id(actors, actor_id):
        raise ValueError("Actor not found")

    instruction = (
        get_next_id(instructions),
        get_current_time(),
        input_text,
        actor_id,
        description,
        tags,
        stage,
    )

    instructions.append(instruction)
    return instruction


def get_instructions() -> list:
    return instructions


def delete_instruction(uid: int) -> bool:
    for instruction in instructions:
        if instruction[0] == uid:
            instructions.remove(instruction)
            return True

    raise ValueError("Instruction not found")


def update_instruction(
        uid: int,
        input_text: str,
        actor_id: int,
        description: str,
        tags: str,
        stage: str,
) -> tuple:
    if not has_id(actors, actor_id):
        raise ValueError("Actor not found")

    for index, instruction in enumerate(instructions):
        if instruction[0] == uid:
            updated_instruction = (
                instruction[0],
                instruction[1],
                input_text,
                actor_id,
                description,
                tags,
                stage,
            )

            instructions[index] = updated_instruction
            return updated_instruction

    raise ValueError("Instruction not found")


def create_response(
        output: str,
        stage: str,
        failure: str,
        instruction_id: int,
) -> tuple:
    if not has_id(instructions, instruction_id):
        raise ValueError("Instruction not found")

    response = (
        get_next_id(responses),
        get_current_time(),
        output,
        stage,
        failure,
        instruction_id,
    )

    responses.append(response)
    return response


def get_responses() -> list:
    return responses


def delete_response(uid: int) -> bool:
    for response in responses:
        if response[0] == uid:
            responses.remove(response)
            return True

    raise ValueError("Response not found")


def update_response(
        uid: int,
        output: str,
        stage: str,
        failure: str,
        instruction_id: int,
) -> tuple:
    if not has_id(instructions, instruction_id):
        raise ValueError("Instruction not found")

    for index, response in enumerate(responses):
        if response[0] == uid:
            updated_response = (
                response[0],
                response[1],
                output,
                stage,
                failure,
                instruction_id,
            )

            responses[index] = updated_response
            return updated_response

    raise ValueError("Response not found")


def get_recent_responses() -> list:
    current_time = get_current_time()
    result = []

    for instruction in instructions:
        if instruction[1] >= current_time - SIX_MINUTES:
            for response in responses:
                if instruction[0] == response[5]:
                    result.append(
                        (
                            instruction[4],
                            response[2],
                        )
                    )

    return result


def read_instruction_data() -> tuple:
    input_text = input("input: ")
    actor_id = int(input("actor id: "))
    description = input("description: ")
    tags = input("tags: ")
    stage = input("stage: ")

    return (
        input_text,
        actor_id,
        description,
        tags,
        stage,
    )


def read_response_data() -> tuple:
    output = input("output: ")
    stage = input("stage: ")
    failure = input("failure: ")
    instruction_id = int(input("instruction id: "))

    return (
        output,
        stage,
        failure,
        instruction_id,
    )


def handle_actor_command(command: str) -> bool:
    match command:
        case "create_actor":
            platform = input("platform: ")
            user_agent = input("user agent: ")
            print(create_actor(platform, user_agent))

        case "get_actors":
            print(get_actors())

        case "delete_actor":
            uid = int(input("uid: "))
            print(delete_actor(uid))

        case "update_actor":
            uid = int(input("uid: "))
            platform = input("platform: ")
            user_agent = input("user agent: ")
            print(update_actor(uid, platform, user_agent))

        case _:
            return False

    return True


def handle_instruction_command(command: str) -> bool:
    match command:
        case "create_instruction":
            data = read_instruction_data()
            print(create_instruction(*data))

        case "get_instructions":
            print(get_instructions())

        case "delete_instruction":
            uid = int(input("uid: "))
            print(delete_instruction(uid))

        case "update_instruction":
            uid = int(input("uid: "))
            data = read_instruction_data()
            print(update_instruction(uid, *data))

        case _:
            return False

    return True


def handle_response_command(command: str) -> bool:
    match command:
        case "create_response":
            data = read_response_data()
            print(create_response(*data))

        case "get_responses":
            print(get_responses())

        case "delete_response":
            uid = int(input("uid: "))
            print(delete_response(uid))

        case "update_response":
            uid = int(input("uid: "))
            data = read_response_data()
            print(update_response(uid, *data))

        case _:
            return False

    return True


def repl() -> None:
    while True:
        command = input("> ").strip()

        if command == "exit":
            break

        try:
            if handle_actor_command(command):
                continue

            if handle_instruction_command(command):
                continue

            if handle_response_command(command):
                continue

            if command == "recent":
                print(get_recent_responses())
                continue

            print("Unknown command")

        except ValueError as error:
            print("Error:", error)


if __name__ == "__main__":
    repl()
