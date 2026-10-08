"""Small, independently written protobuf wire codec for the documented gateway.

No generated descriptors, route tables, or code from another Muse CLI are shipped.
Only protobuf wire types 0, 1, 2, and 5 are accepted. Unknown fields are skipped.
"""

from .errors import BridgeError

MAX_MESSAGE = 8 * 1024 * 1024


def bad():
    return BridgeError("PROTOCOL_ERROR", "Malformed or oversized gateway message.")


def varint(number: int) -> bytes:
    if not 0 <= number < 1 << 64:
        raise ValueError("unsigned 64-bit integer required")
    parts = bytearray()
    while number >= 128:
        parts.append((number & 127) | 128)
        number >>= 7
    parts.append(number)
    return bytes(parts)


def read_varint(data: bytes, offset: int):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise bad()
        byte = data[offset]
        offset += 1
        if shift == 63 and byte > 1:
            raise bad()
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
    raise bad()


def integer(field: int, value: int):
    return varint(field << 3) + varint(value)


def blob(field: int, value: bytes | str):
    if isinstance(value, str):
        value = value.encode("utf-8")
    return varint((field << 3) | 2) + varint(len(value)) + value


def fields(data: bytes):
    if len(data) > MAX_MESSAGE:
        raise bad()
    cursor = 0
    result = {}
    while cursor < len(data):
        tag, cursor = read_varint(data, cursor)
        field, kind = tag >> 3, tag & 7
        if not 0 < field < 1 << 29:
            raise bad()
        if kind == 0:
            value, cursor = read_varint(data, cursor)
        else:
            if kind == 2:
                size, cursor = read_varint(data, cursor)
            elif kind in (1, 5):
                size = 8 if kind == 1 else 4
            else:
                raise bad()
            if cursor + size > len(data):
                raise bad()
            value = data[cursor : cursor + size]
            cursor += size
        result.setdefault(field, []).append(value)
    return result


def last(items, field, default=None):
    return items.get(field, [default])[-1]


def request(stream: int, verb: str, path: str, body: bytes = b""):
    header = blob(1, "content-type") + blob(2, "application/json")
    application = blob(1, verb) + blob(2, path) + blob(3, header)
    application += blob(4, body) + integer(5, 1)
    frame = integer(1, stream) + blob(2, application)
    # Service 0 is daemon. Explicitly encode the default for clarity.
    return integer(1, 0) + blob(2, frame)


def chunks(payload: bytes, chunk_id: int, max_payload: int = 48_000):
    if not 1 <= max_payload <= 48_000 or len(payload) > MAX_MESSAGE:
        raise bad()
    total = max(1, (len(payload) + max_payload - 1) // max_payload)
    for index in range(total):
        piece = payload[index * max_payload : (index + 1) * max_payload]
        yield (integer(1, chunk_id) + integer(2, index) + integer(3, total) + blob(4, piece))


class Reassembly:
    """Bounded reassembly of sequential/interleaved transport chunks."""

    def __init__(self):
        self.pending = {}
        self.buffered = 0

    def accept(self, data):
        item = fields(data)
        ident = last(item, 1, 0)
        index = last(item, 2, 0)
        total = last(item, 3, 0)
        payload = last(item, 4, b"")
        if not all(isinstance(x, int) for x in (ident, index, total)):
            raise bad()
        if not isinstance(payload, bytes) or not 1 <= total <= 256 or not 0 <= index < total:
            raise bad()
        if ident not in self.pending:
            if len(self.pending) >= 16:
                raise bad()
            self.pending[ident] = (total, {})
        expected, pieces = self.pending[ident]
        if expected != total or index in pieces:
            raise bad()
        self.buffered += len(payload)
        if self.buffered > MAX_MESSAGE:
            raise bad()
        pieces[index] = payload
        if len(pieces) != total:
            return None
        result = b"".join(pieces[i] for i in range(total))
        del self.pending[ident]
        self.buffered -= len(result)
        return result


def response(data):
    envelope = fields(data)
    payload = last(envelope, 1)
    if not isinstance(payload, bytes):
        raise bad()
    frame = fields(payload)
    stream = last(frame, 1, 0)
    if not isinstance(stream, int):
        raise bad()
    if 5 in frame:
        # Do not echo the server's free-form reason: it can contain private data.
        raise BridgeError("STREAM_RESET", "The gateway reset the request stream.")
    if 3 in frame:
        part = fields(last(frame, 3))
        return stream, last(part, 1, 0), last(part, 3, b""), bool(last(part, 4, 0))
    if 4 in frame:
        part = fields(last(frame, 4))
        return stream, None, last(part, 1, b""), bool(last(part, 2, 0))
    return stream, None, b"", False
