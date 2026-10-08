import pytest

from musebridge import wire
from musebridge.errors import BridgeError
from musebridge.trust import check_standard_payload

KEY = b"k" * 32
BUNDLE = wire.blob(2, wire.blob(1, KEY))


def test_non_tee_bundle_is_accepted_only_when_bound_to_noise_peer():
    assert check_standard_payload(BUNDLE, KEY) == "standard_non_tee"
    assert check_standard_payload(wire.integer(1, 0) + BUNDLE, KEY) == "standard_non_tee"


def test_mismatched_public_key_is_rejected():
    with pytest.raises(BridgeError) as error:
        check_standard_payload(BUNDLE, b"other" * 6 + b"xx")
    assert error.value.code == "PEER_KEY_MISMATCH"


@pytest.mark.parametrize(
    "payload",
    [
        wire.integer(1, 1) + BUNDLE,
        BUNDLE + wire.blob(10, b"snp-evidence"),
        BUNDLE + wire.blob(20, b"image-manifest"),
        BUNDLE + wire.blob(2, wire.blob(1, KEY)),
        wire.blob(2, wire.blob(1, b"short")),
        wire.blob(2, wire.blob(1, KEY) + wire.blob(2, b"unsolicited-nonce")),
        wire.blob(1, b"attestation") + wire.integer(2, 1) + wire.blob(3, b"nonce" * 6 + b"xx"),
        b"unknown-format",
    ],
)
def test_confidential_unknown_and_malformed_payloads_stay_rejected(payload):
    with pytest.raises(BridgeError) as error:
        check_standard_payload(payload, KEY)
    assert error.value.code == "UNSUPPORTED_VM_MODE"


def test_empty_legacy_standard_payload_remains_compatible():
    assert check_standard_payload(b"", KEY) == "legacy_standard"
