"""Classify Muse's attestation envelope without bypassing confidential-VM checks."""

import hmac

from . import wire
from .errors import BridgeError


def unsupported():
    return BridgeError(
        "UNSUPPORTED_VM_MODE",
        "This VM requires an unsupported trust flow.",
        "Confidential or unfamiliar handshake formats need a verified implementation.",
    )


def check_standard_payload(payload: bytes, peer_key: bytes):
    if not payload:
        return "legacy_standard"
    try:
        bundle = wire.fields(payload)
        # AttestationBundle.platform: NON_TEE = 0; report_data_input = field 2.
        # Accept only these known fields. SNP evidence and RV challenges remain refused.
        if set(bundle) - {1, 2} or len(bundle.get(1, [])) > 1 or len(bundle.get(2, [])) != 1:
            raise unsupported()
        if wire.last(bundle, 1, 0) != 0:
            raise unsupported()
        encoded = wire.last(bundle, 2)
        if not isinstance(encoded, bytes):
            raise unsupported()
        report = wire.fields(encoded)
        if set(report) != {1} or len(report[1]) != 1:
            raise unsupported()
        key = wire.last(report, 1)
        if not isinstance(key, bytes) or len(key) != 32 or len(peer_key) != 32:
            raise unsupported()
        if not hmac.compare_digest(key, peer_key):
            raise BridgeError(
                "PEER_KEY_MISMATCH", "Handshake payload does not match the Noise peer key."
            )
        return "standard_non_tee"
    except BridgeError as error:
        if error.code == "PROTOCOL_ERROR":
            raise unsupported() from None
        raise
