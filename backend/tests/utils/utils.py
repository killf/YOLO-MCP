import random
import string


def random_lower_string() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=16))


def random_username() -> str:
    return f"{random_lower_string()}@{random_lower_string()}.com"


def empty_project_upload(project_id: int, input_filename: str) -> str:
    from backend.common.storage import get_storage

    key = f"projects/{project_id}/images/{input_filename}"
    get_storage().delete(key)
    return key
