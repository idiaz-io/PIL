"""Runs inside AXO's interpreter and reports what AXO's normalisers produce.

This file is executed by ``scripts/parity.py`` as a subprocess, using AXO's own Python
so that AXO's dependencies (pydantic, httpx, fastapi, sqlalchemy) are available. PIL's
virtualenv does not have them and must not — I-3 means PIL never depends on a product,
and that includes its dependency tree.

It reads a JSON job on stdin and writes JSON results on stdout:

    in:  {"axo_path": "...", "frozen_iso": "...", "cases": [{"source": ..., "payload": ...}]}
    out: {"results": [{"ok": true, "projection": {...}} | {"ok": false, "error": "..."}]}

Nothing here is imported by PIL. It is data in, data out, across a process boundary.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime


def build_frozen_datetime(instant: datetime) -> type:
    """A ``datetime`` subclass whose ``utcnow()`` does not move.

    AXO reaches for ``datetime.utcnow()`` whenever a payload has no usable timestamp, so
    without this the same fixture produces a different answer on every run and parity is
    unprovable. Patching the name in each module is the only way in — ``datetime`` itself
    is a C type and cannot be monkeypatched.
    """
    frozen_naive = instant.astimezone(UTC).replace(tzinfo=None)

    class FrozenDatetime(datetime):
        @classmethod
        def utcnow(cls) -> datetime:  # type: ignore[override]
            return frozen_naive

        @classmethod
        def now(cls, tz=None):  # type: ignore[override, no-untyped-def]
            return instant.astimezone(tz) if tz else frozen_naive

    return FrozenDatetime


def project(alert: object) -> dict:
    """Reduce an AXO ``StandardAlert`` to the fields PIL also produces.

    AXO has two classes of this name with different field names — the Pydantic one calls
    the alert text ``description``, the dataclass one calls it ``message``. AXO itself
    reconciles them by reflection at `routes/webhook.py:99`; so does this.

    ``client_id``/``client_name`` are reported separately rather than as part of the
    comparison: PIL takes the tenant from configuration, so those are the one field
    deliberately excluded (ADR-0004). They are carried through so the harness can report
    what AXO would have used.
    """
    text = getattr(alert, "description", None)
    if text is None:
        text = getattr(alert, "message", "")

    timestamp = getattr(alert, "timestamp", None)
    if isinstance(timestamp, datetime):
        utc = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
        utc = utc.astimezone(UTC)
        rendered = (
            f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}"
            f"T{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}"
            f".{utc.microsecond:06d}Z"
        )
    else:
        rendered = str(timestamp)

    history = getattr(alert, "device_history", []) or []

    return {
        "alert_id": str(getattr(alert, "alert_id", "")),
        "device_id": str(getattr(alert, "device_id", "")),
        "device_name": str(getattr(alert, "device_name", "")),
        "severity": str(getattr(alert, "severity", "")),
        "category": str(getattr(alert, "category", "")),
        "message": str(text),
        "occurred_at": rendered,
        "device_history": [dict(entry) for entry in history if isinstance(entry, dict)],
        "raw_payload": dict(getattr(alert, "raw_payload", {}) or {}),
        # Excluded from the comparison; reported for the shadow-mode tenant report.
        "_axo_tenant_id": str(getattr(alert, "client_id", "")),
        "_axo_tenant_name": str(getattr(alert, "client_name", "")),
    }


def load_translators(axo_path: str, frozen: type) -> dict:
    """Import AXO's normalisers and freeze the clock in each module that uses one."""
    platform = os.path.join(axo_path, "msp-platform")
    for entry in (platform, axo_path):
        if entry not in sys.path:
            sys.path.insert(0, entry)

    # Minimal environment so importing backend.config does not fail on a missing .env.
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused/unused")
    os.environ.setdefault("ANTHROPIC_API_KEY", "")

    import asyncio

    translators = {}

    from integrations.sciencelogic import normaliser as sl_normaliser

    sl_normaliser.datetime = frozen
    translators["sciencelogic"] = sl_normaliser.normalise_sciencelogic_alert

    from integrations.connectwise import ticket_normaliser as cw_normaliser

    cw_normaliser.datetime = frozen
    translators["connectwise"] = cw_normaliser.normalise_connectwise_alert

    from backend.integrations import fleet_healing_adapter as fleet_mod

    fleet_mod.datetime = frozen

    async def _no_config(self) -> None:
        """`normalize_alert` calls `_ensure_config()`, which reads the database.

        It has no effect on the translation, so it is stubbed rather than served — the
        alternative is standing up Postgres to prove a pure function.
        """

    fleet_mod.FleetHealingAdapter._ensure_config = _no_config
    _fleet = fleet_mod.FleetHealingAdapter()
    translators["fleet"] = lambda raw: asyncio.run(_fleet.normalize_alert(raw))

    from backend.integrations import sl1_adapter as sl1_mod

    sl1_mod.datetime = frozen
    _sl1 = sl1_mod.SL1Adapter(demo_mode=True)
    translators["sl1"] = lambda raw: asyncio.run(_sl1.normalize_alert(raw))

    from backend.integrations import addigy_adapter as addigy_mod

    addigy_mod.datetime = frozen
    _addigy = addigy_mod.AddigyAdapter(demo_mode=True)
    translators["addigy"] = lambda raw: asyncio.run(_addigy.normalize_alert(raw))

    try:
        from backend.routes import webhook as webhook_mod

        webhook_mod.datetime = frozen
        translators["legacy"] = webhook_mod._legacy_normalise
    except Exception as exc:
        # routes/webhook.py drags in FastAPI, SQLAlchemy and the DB layer. If it will
        # not import here, say so rather than silently reporting parity for five of six
        # sources as though it were all of them.
        translators["legacy"] = ("unavailable", f"{type(exc).__name__}: {exc}")

    return translators


def main() -> int:
    job = json.load(sys.stdin)
    frozen = build_frozen_datetime(datetime.fromisoformat(job["frozen_iso"]))

    try:
        translators = load_translators(job["axo_path"], frozen)
    except Exception as exc:
        json.dump({"fatal": f"{type(exc).__name__}: {exc}"}, sys.stdout)
        return 1

    results = []
    for case in job["cases"]:
        translator = translators.get(case["source"])
        if translator is None:
            results.append({"ok": False, "error": f"no AXO translator for {case['source']!r}"})
            continue
        if isinstance(translator, tuple):
            results.append({"ok": False, "error": f"translator unavailable: {translator[1]}"})
            continue
        try:
            results.append({"ok": True, "projection": project(translator(case["payload"]))})
        except Exception as exc:
            # An exception is a legitimate outcome to compare — several of AXO's
            # normalisers raise on payloads the harness must still classify.
            results.append({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    json.dump({"results": results}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
