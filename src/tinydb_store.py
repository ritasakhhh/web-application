from tinydb import Query, TinyDB, where

from first_step import get_current_time

SIX_MINUTES = 6 * 60


class TinyDbStore:
    def __init__(self, path):
        self.db = TinyDB(path, encoding="utf-8", ensure_ascii=False)

    def close(self):
        self.db.close()

    def find(self, table_name, **filters):
        table = self.db.table(table_name)
        filters = {
            key: value for key, value in filters.items() if value is not None
        }
        if filters:
            return table.search(Query().fragment(filters))
        return table.all()

    def get(self, table_name, uid):
        record = self.db.table(table_name).get(where("uid") == uid)
        if record is None:
            raise ValueError(f"{table_name} not found")
        return record

    def create(self, table_name, uid, **fields):
        table = self.db.table(table_name)
        if table.contains(where("uid") == uid):
            raise ValueError("Identifier already exists")
        record = {"uid": uid, "datetime": get_current_time(), **fields}
        table.insert(record)
        return record

    def update(self, table_name, uid, **changes):
        record = self.get(table_name, uid)
        self.db.table(table_name).update(changes, doc_ids=[record.doc_id])
        return {**record, **changes}

    def delete(self, table_name, field, value):
        return self.db.table(table_name).remove(where(field) == value)

    def get_recent_responses(self):
        cutoff = get_current_time() - SIX_MINUTES
        instructions = self.db.table("Instruction").search(
            where("datetime") >= cutoff,
        )
        result = []
        for instruction in instructions:
            responses = self.find("Response", instruction=instruction["uid"])
            for response in responses:
                result.append({
                    "description": instruction["description"],
                    "output": response["output"],
                })
        return result
