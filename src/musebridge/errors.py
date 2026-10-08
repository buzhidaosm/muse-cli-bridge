from dataclasses import dataclass


@dataclass
class BridgeError(Exception):
    code: str
    message: str
    hint: str = ""
    delivery: str | None = None

    def __str__(self):
        return self.message


def failure(error: BridgeError):
    item = {"code": error.code, "message": error.message}
    if error.hint:
        item["hint"] = error.hint
    if error.delivery:
        item["delivery"] = error.delivery
    return {"ok": False, "error": item}


def success(data):
    return {"ok": True, "data": data}
