# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Phase 6 engine behaviour on phone calls, with synthetic audio and a fake backend: opt-out, transfer (success
and failure), keypad tones, the recording notice and consent answer, and the fallback message."""

import asyncio

from xplovoice_engine.audio import silence, tone
from xplovoice_engine.channel import ScriptedChannel
from xplovoice_engine.session import MESSAGES, CallSession

from .test_engine import ESCALATION, SPEED, FakeBackend, agent_lines, boot

ONE_TURN = [silence(1500), tone(800), silence(5000)]
PHONE = {
    "phone": True,
    "direction": "outbound",
    "can_transfer": True,
    "transfer_targets": ["Front desk"],
    "opt_out_phrases": ["stop calling", "don't call me"],
    "fallback_message": None,
    "recording": {"policy": "off", "consent_message": ""},
    "keypad": True,
}


class PhoneBackend(FakeBackend):
    def __init__(self, *a, transfer_ok=True, **kw):
        super().__init__(*a, **kw)
        self.transfer_ok = transfer_ok
        self.transfers: list[int] = []
        self.opt_outs: list[str] = []
        self.consents: list[tuple[str, str]] = []

    async def transfer(self, target):
        self.transfers.append(target)
        return {"ok": self.transfer_ok, "reason": None if self.transfer_ok else "refused"}

    async def opt_out(self, said):
        self.opt_outs.append(said)

    async def consent(self, purpose, status, said):
        self.consents.append((purpose, status))


def phone_boot(**tel):
    return boot(telephony=PHONE | tel)


def run(backend, script, b, *, tail_ms=1500, keys=None):
    ch = ScriptedChannel(script, speed=SPEED, tail_ms=tail_ms)
    ch.dtmf = asyncio.Queue()  # type: ignore[attr-defined]

    async def go():
        session = CallSession(backend, ch, b, worker_id="w-test")
        if keys:

            async def press():
                for delay, k in keys:
                    await asyncio.sleep(delay / SPEED)
                    ch.dtmf.put_nowait(k)  # type: ignore[attr-defined]

            asyncio.get_running_loop().create_task(press())
        return await session.run()

    return asyncio.run(go()), ch


def test_opt_out_phrase_stops_the_call_and_tells_the_platform():
    be = PhoneBackend(heard=["Please STOP calling me"])
    reason, _ = run(be, ONE_TURN, phone_boot())
    assert reason == "opted_out" and be.opt_outs == ["Please STOP calling me"]
    assert agent_lines(be)[-1]["text"] == MESSAGES["opted_out"] and be.llm_messages == []


def test_opt_out_phrases_are_off_on_browser_calls():
    be = PhoneBackend(heard=["stop calling me"])
    reason, _ = run(be, ONE_TURN, boot())
    assert reason == "caller_hangup" and be.opt_outs == []


def test_transfer_success_ends_the_agent_leg():
    be = PhoneBackend(heard=["get me the manager"])
    esc = ESCALATION | {"action": "transfer", "message": "Please hold while I connect you."}
    reason, _ = run(be, ONE_TURN, boot(escalation=esc, telephony=PHONE))
    assert reason == "transferred" and be.transfers == [0]
    assert agent_lines(be)[-1]["text"] == "Please hold while I connect you."


def test_failed_transfer_comes_back_and_takes_a_message():
    be = PhoneBackend(heard=["get me the manager"], transfer_ok=False)
    esc = ESCALATION | {"action": "transfer", "message": "Please hold while I connect you."}
    reason, _ = run(be, ONE_TURN, boot(escalation=esc, telephony=PHONE), tail_ms=6000)
    assert be.transfers == [0] and reason == "caller_hangup"  # the conversation went on
    assert [a["text"] for a in agent_lines(be)][-2:] == [
        "Please hold while I connect you.",
        MESSAGES["transfer_failed"],
    ]
    asks = [e["data"] for e in be.events if e["type"] == "escalation.requested"]
    assert asks[-1] == {"trigger": "transfer_failed", "action": "take_message"}


def test_keypad_digits_become_a_typed_reply_and_zero_asks_for_a_person():
    be = PhoneBackend()
    reason, _ = run(be, [silence(1500)], phone_boot(), tail_ms=6000, keys=[(1.5, "1"), (0.1, "2"), (0.1, "#")])
    caller = [s["text"] for s in be.segments if s["speaker"] == "caller"]
    assert caller == ["[keypad] 1 2"]
    assert "pressed keys on the keypad: 1 2" in be.llm_messages[0][-1]["content"]
    assert [e["data"]["digit"] for e in be.events if e["type"] == "dtmf"] == ["1", "2", "#"]

    be = PhoneBackend()
    reason, _ = run(be, [silence(1500)], boot(escalation=ESCALATION, telephony=PHONE), tail_ms=6000, keys=[(1.5, "0")])
    assert reason == "escalated"
    assert [e["data"]["trigger"] for e in be.events if e["type"] == "escalation.requested"] == ["keypad_0"]


AFTER_NOTICE = [silence(6000), tone(800), silence(5000)]


def test_recording_notice_and_consent_answer():
    rec = {"policy": "ask_consent", "consent_message": "This call may be recorded. Say no if you'd prefer not."}
    be = PhoneBackend(heard=["No, I don't want that"])
    run(be, AFTER_NOTICE, phone_boot(recording=rec))
    assert agent_lines(be)[0]["text"] == "This call may be recorded. Say no if you'd prefer not. Hello there."
    assert agent_lines(be)[0]["interrupted"] is False
    assert be.consents == [("recording", "declined")]
    be = PhoneBackend(heard=["sure, that's fine"])
    run(be, AFTER_NOTICE, phone_boot(recording=rec))
    assert be.consents == [("recording", "granted")]
    be = PhoneBackend(heard=["hello"])
    run(be, AFTER_NOTICE, phone_boot(recording=rec | {"policy": "record"}))
    assert be.consents == [] and agent_lines(be)[0]["text"].startswith("This call may be recorded.")


def test_fallback_message_is_said_then_the_call_ends():
    be = PhoneBackend()
    reason, _ = run(
        be, [silence(500)], phone_boot(fallback_message="Sorry, we're busy. Please call back."), tail_ms=6000
    )
    assert reason == "unavailable"
    assert [a["text"] for a in agent_lines(be)] == ["Sorry, we're busy. Please call back."]
