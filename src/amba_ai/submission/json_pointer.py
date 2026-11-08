from __future__ import annotations
from typing import Any
class JsonPointerError(ValueError): pass

def resolve_json_pointer(document: Any, pointer: str) -> Any:
    if pointer == "": return document
    if not pointer.startswith("/"): raise JsonPointerError("JSON pointer must be empty or start with /")
    value=document
    for raw in pointer[1:].split("/"):
        token=raw.replace("~1","/").replace("~0","~")
        if isinstance(value,list):
            try:value=value[int(token)]
            except (ValueError,IndexError) as exc:raise JsonPointerError(f"invalid list token: {token}") from exc
        elif isinstance(value,dict):
            if token not in value:raise JsonPointerError(f"missing object token: {token}")
            value=value[token]
        else:raise JsonPointerError(f"cannot traverse token {token} through {type(value).__name__}")
    return value
