"""Build the immutable catalog snapshot a decision is made against.

A snapshot is the merchant's truth at one moment, content-hashed so a decision
can name exactly what it was made against. Everything downstream reads from a
snapshot rather than from the live catalog: prices change, stock changes, and a
decision that cannot say which prices it saw is not replayable.
"""

from __future__ import annotations

from pathlib import Path

from custodian.clock import utc_now
from custodian.ingest.loader import LoadReport, load_csv
from custodian.ingest.taxonomy import Taxonomy, default_taxonomy
from custodian.schemas.catalog import CatalogItem, CatalogSnapshot


def build_snapshot(
    items: list[CatalogItem],
    *,
    merchant_id: str,
    snapshot_id: str | None = None,
    taken_at: str | None = None,
    lexicon_version: str,
) -> CatalogSnapshot:
    """Assemble a snapshot. ``snapshot_id`` defaults to the content hash."""
    moment = taken_at or utc_now()
    provisional = CatalogSnapshot(
        snapshot_id=snapshot_id or "pending",
        merchant_id=merchant_id,
        taken_at=moment,
        items=tuple(items),
        lexicon_version=lexicon_version,
    )
    if snapshot_id is not None:
        return provisional
    # Name the snapshot after its content, so identical catalogs at the same
    # instant are one snapshot and a changed catalog is visibly a different one.
    return provisional.model_copy(update={"snapshot_id": f"snap-{provisional.digest()[:16]}"})


def ingest_csv(
    path: Path | str,
    *,
    merchant_id: str,
    taken_at: str | None = None,
    taxonomy: Taxonomy | None = None,
) -> tuple[CatalogSnapshot, LoadReport]:
    """Messy CSV in, agent-readable snapshot out."""
    tax = taxonomy or default_taxonomy()
    items, report = load_csv(path, taxonomy=tax)
    snapshot = build_snapshot(
        items, merchant_id=merchant_id, taken_at=taken_at, lexicon_version=tax.lexicon_version
    )
    return snapshot, report


def agent_feed(snapshot: CatalogSnapshot) -> list[dict[str, object]]:
    """The view an agent is given.

    Deliberately narrow. It carries what a buyer needs to build a cart and
    nothing else — no raw name, no sanitizer findings, no flagged spans. Those
    stay in the snapshot as evidence; handing an agent the text that was
    stripped would defeat the point of stripping it.
    """
    return [
        {
            "item_id": item.item_id,
            "name": item.name,
            "price_paise": item.price_paise,
            "in_stock": item.in_stock,
            "category": item.category,
            "unit_quantity": item.unit_quantity,
            "unit": item.unit,
        }
        for item in snapshot.items
        if item.in_stock
    ]
