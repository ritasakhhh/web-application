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