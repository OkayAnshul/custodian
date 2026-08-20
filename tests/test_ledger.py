"""The ledger is evidence, so these tests attack it rather than exercise it."""

import json
import sqlite3

import pytest

from custodian.canonical import GENESIS_HASH, CanonicalisationError
from custodian.ledger.chain import EventType, Ledger, LedgerError, compute_hash
from custodian.ledger.verify import verify_chain


@pytest.fixture
def ledger() -> Ledger:
    return Ledger.in_memory()


@pytest.fixture
def file_ledger(tmp_path):
    path = tmp_path / "ledger.db"
    led = Ledger.open(path)
    yield led, path
    led.close()


def _append(led: Ledger, n: int = 3) -> None:
    for i in range(n):
        led.append(
            EventType.DECISION_MADE,
            f"req-{i}",
            observed={"cart_total_paise": 199_900 + i},
            inferred={"outcome": "approve", "confidence_bp": 9_200},
        )


def test_first_event_chains_to_genesis(ledger):
    event = ledger.append(EventType.INTENT_RECEIVED, "req-1", observed={"goal": "thai curry"})
    assert event.prev_hash == GENESIS_HASH
    assert event.seq == 1


def test_each_event_links_to_its_predecessor(ledger):
    first = ledger.append(EventType.INTENT_RECEIVED, "req-1", observed={"a": 1})
    second = ledger.append(EventType.DECISION_MADE, "req-1", observed={"b": 2})
    assert second.prev_hash == first.hash
    assert ledger.head() == second.hash


def test_intact_chain_verifies(ledger):
    _append(ledger, 5)
    result = verify_chain(ledger)
    assert result.ok, str(result)
    assert result.events_checked == 5


def test_empty_chain_verifies_at_genesis(ledger):
    result = verify_chain(ledger)
    assert result.ok
    assert result.head == GENESIS_HASH


# --- tamper evidence -------------------------------------------------------

def test_editing_a_payload_behind_the_application_is_detected(file_ledger):
    """An attacker with file access drops the triggers first. The hash still tells."""
    led, path = file_ledger
    _append(led, 3)
    led.close()

    raw = sqlite3.connect(path)
    raw.execute("DROP TRIGGER ledger_immutable_update")
    raw.execute("UPDATE ledger SET payload = ? WHERE seq = 2",
                (json.dumps({"observed": {"cart_total_paise": 1}, "inferred": {}}),))
    raw.commit()
    raw.close()

    result = verify_chain(Ledger.open(path))
    assert not result.ok
    assert result.breaks[0].kind == "HASH_MISMATCH"
    assert result.breaks[0].seq == 2


def test_removing_an_event_breaks_the_link(file_ledger):
    led, path = file_ledger
    _append(led, 3)
    led.close()

    raw = sqlite3.connect(path)
    raw.execute("DROP TRIGGER ledger_immutable_delete")
    raw.execute("DELETE FROM ledger WHERE seq = 2")
    raw.commit()
    raw.close()

    result = verify_chain(Ledger.open(path))
    assert not result.ok
    assert result.breaks[0].kind == "LINK_MISMATCH"


def test_verification_reports_the_first_break_not_the_cascade(file_ledger):
    """One edit invalidates everything after it; naming all of them buries the edit."""
    led, path = file_ledger
    _append(led, 6)
    led.close()

    raw = sqlite3.connect(path)
    raw.execute("DROP TRIGGER ledger_immutable_update")
    raw.execute("UPDATE ledger SET ts = '1999-01-01T00:00:00+00:00' WHERE seq = 2")
    raw.commit()
    raw.close()

    result = verify_chain(Ledger.open(path))
    assert not result.ok
    assert len(result.breaks) == 1
    assert result.breaks[0].seq == 2


def test_timestamps_are_covered_by_the_hash(ledger):
    """A timestamp that can be altered undetectably is not tamper-evident."""
    payload = {"observed": {"a": 1}, "inferred": {}}
    common = dict(prev_hash=GENESIS_HASH, event_id="e1", request_id="r1",
                  event_type="DECISION_MADE", payload=payload)
    assert compute_hash(ts="2026-08-21T00:00:00+00:00", **common) != compute_hash(
        ts="2026-08-22T00:00:00+00:00", **common
    )


# --- append-only enforcement ----------------------------------------------

def test_update_is_refused_by_the_database(ledger):
    _append(ledger, 1)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger._conn.execute("UPDATE ledger SET payload = '{}' WHERE seq = 1")


def test_delete_is_refused_by_the_database(ledger):
    _append(ledger, 1)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger._conn.execute("DELETE FROM ledger WHERE seq = 1")


# --- payload discipline ----------------------------------------------------

def test_observed_and_inferred_are_kept_apart(ledger):
    event = ledger.append(
        EventType.DECISION_MADE,
        "req-1",
        observed={"catalog_price_paise": 19_900},
        inferred={"substitution_score_bp": 8_500},
    )
    assert event.observed == {"catalog_price_paise": 19_900}
    assert event.inferred == {"substitution_score_bp": 8_500}
    assert set(event.payload) == {"observed", "inferred"}


def test_inferred_defaults_to_empty_never_missing(ledger):
    event = ledger.append(EventType.SNAPSHOT_TAKEN, "req-1", observed={"items": 12})
    assert event.inferred == {}


def test_a_float_score_cannot_reach_the_chain(ledger):
    with pytest.raises(CanonicalisationError):
        ledger.append(EventType.DECISION_MADE, "req-1",
                      observed={}, inferred={"confidence": 0.92})


def test_a_rejected_append_leaves_no_trace(ledger):
    _append(ledger, 2)
    head_before = ledger.head()
    with pytest.raises(CanonicalisationError):
        ledger.append(EventType.DECISION_MADE, "req-1", observed={"x": 1.5})
    assert ledger.head() == head_before
    assert len(ledger) == 2


def test_unknown_event_types_are_refused(ledger):
    with pytest.raises(LedgerError):
        ledger.append("MADE_IT_UP", "req-1", observed={})  # type: ignore[arg-type]


def test_an_event_must_correlate_to_a_request(ledger):
    with pytest.raises(LedgerError):
        ledger.append(EventType.DECISION_MADE, "", observed={})


# --- reading ---------------------------------------------------------------

def test_reads_one_request_in_order(ledger):
    ledger.append(EventType.INTENT_RECEIVED, "req-A", observed={"n": 1})
    ledger.append(EventType.DECISION_MADE, "req-B", observed={"n": 2})
    ledger.append(EventType.PAYMENT_SETTLED, "req-A", observed={"n": 3})

    events = ledger.read("req-A")
    assert [e.event_type for e in events] == [EventType.INTENT_RECEIVED, EventType.PAYMENT_SETTLED]
    assert [e.seq for e in events] == sorted(e.seq for e in events)


def test_the_same_inputs_produce_the_same_chain(tmp_path):
    """Determinism, with time and ids injected — the basis of replay."""
    def build(path):
        led = Ledger.open(path)
        for i in range(3):
            led.append(EventType.DECISION_MADE, "req-1",
                       observed={"i": i}, inferred={"score_bp": 9_000},
                       ts="2026-08-21T00:00:00+00:00", event_id=f"evt-{i}")
        head = led.head()
        led.close()
        return head

    assert build(tmp_path / "a.db") == build(tmp_path / "b.db")
