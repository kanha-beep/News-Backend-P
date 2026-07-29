from app.core.exceptions import bad_request


def read_string(
    value,
    field_name: str,
    *,
    required: bool = False,
    min_length: int = 0,
    max_length: int = 500,
    lowercase: bool = False,
) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not normalized:
        if required:
            raise bad_request(f"{field_name} is required")
        return ""

    if len(normalized) < min_length:
        raise bad_request(f"{field_name} must be at least {min_length} characters")
    if len(normalized) > max_length:
        raise bad_request(f"{field_name} must be {max_length} characters or fewer")
    return normalized.lower() if lowercase else normalized


def read_optional_boolean(value) -> bool:
    return value is True or value == "true"

