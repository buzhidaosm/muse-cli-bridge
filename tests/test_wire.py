import pytest

from musebridge import wire
from musebridge.errors import BridgeError


@pytest.mark.parametrize("value", [0, 1, 127, 128, 300, 2**32, 2**64 - 1])
def test_protobuf_varints(value):
    data = wire.varint(value)
    assert wire.read_varint(data, 0) == (value, len(data))


def test_golden_varint_from_protobuf_spec():
    assert wire.integer(1, 150) == b"\x08\x96\x01"
    assert wire.blob(2, "testing") == b"\x12\x07testing"


@pytest.mark.parametrize("data", [b"\x80", b"\x00", b"\x12\x10ab", b"\x0b", b"\xff" * 12])
def test_malformed_input_rejected(data):
    with pytest.raises(BridgeError):
        wire.fields(data)


def test_unknown_fields_are_preserved():
    parsed = wire.fields(b"\x08\x96\x01\x12\x03abc")
    assert parsed == {1: [150], 2: [b"abc"]}


def test_request_semantics():
    outer = wire.fields(wire.request(17, "GET", "/chat/history?limit=2"))
    assert wire.last(outer, 1) == 0
    frame = wire.fields(wire.last(outer, 2))
    assert wire.last(frame, 1) == 17
    app = wire.fields(wire.last(frame, 2))
    assert wire.last(app, 1) == b"GET"
    assert wire.last(app, 2) == b"/chat/history?limit=2"
    assert wire.last(app, 5) == 1


def test_reassembly_out_of_order_and_interleaved():
    assembler = wire.Reassembly()
    one = list(wire.chunks(b"abcdef", 3, 2))
    two = list(wire.chunks(b"xyz", 4, 2))
    assert assembler.accept(one[2]) is None
    assert assembler.accept(two[0]) is None
    assert assembler.accept(one[0]) is None
    assert assembler.accept(two[1]) == b"xyz"
    assert assembler.accept(one[1]) == b"abcdef"
    assert assembler.buffered == 0


def test_duplicate_chunk_rejected():
    assembler = wire.Reassembly()
    chunk = next(wire.chunks(b"abcdef", 1, 2))
    assembler.accept(chunk)
    with pytest.raises(BridgeError):
        assembler.accept(chunk)


def test_response_and_body_chunks():
    app = wire.integer(1, 200) + wire.blob(3, b'{"x":')
    frame = wire.integer(1, 17) + wire.blob(3, app)
    assert wire.response(wire.blob(1, frame)) == (17, 200, b'{"x":', False)
    chunk = wire.blob(1, b"1}") + wire.integer(2, 1)
    frame = wire.integer(1, 17) + wire.blob(4, chunk)
    assert wire.response(wire.blob(1, frame)) == (17, None, b"1}", True)


def test_server_reason_is_never_exposed():
    frame = wire.integer(1, 1) + wire.blob(5, wire.blob(2, "access_token=PRIVATE"))
    with pytest.raises(BridgeError) as caught:
        wire.response(wire.blob(1, frame))
    assert "PRIVATE" not in str(caught.value)
