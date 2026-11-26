# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Carrier adapters by provider key. 'managed' (numbers from XploVoice) has no adapter until a carrier is
contracted (awaiting configuration)."""

from .base import CarrierAdapter, CarrierError
from .livekit_sip import LiveKitSip
from .simulated import SimulatedCarrier

_ADAPTERS: dict[str, CarrierAdapter] = {"simulated": SimulatedCarrier(), "sip": LiveKitSip()}


def adapter(key: str) -> CarrierAdapter:
    a = _ADAPTERS.get(key)
    if a is None:
        raise CarrierError("This carrier is awaiting configuration.")
    return a
