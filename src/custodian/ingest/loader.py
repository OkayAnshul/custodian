"""Read a merchant's export and normalise it into catalog items.

Real exports are inconsistent in every column at once: prices live in the name
as often as the price field, stock is spelled six ways, categories are missing
or differently cased, and the pack size is embedded in free text. Ingest resolves
all of it deterministically and records what it had to do — an item that was
normalised by guesswork should be visible as such, not silently smoothed over.

Two resolutions are worth stating because they are judgment calls rather than
mechanics:

**Price.** The price *field* wins over a price written in the product name. When
the two disagree the item is flagged ``PRICE_CLAIM``, because copy asserting a
price that contradicts the price field is the shape of a poisoning attempt, and
"the merchant's data entry is sloppy" and "someone is trying to be believed
instead of the price field" are indistinguishable from here.

**Category.** Taken from the taxonomy, not from the merchant's category column.
The column is missing on a sixth of rows and inconsistently cased on the rest,
so it cannot be used for set membership — and set membership is what the gate
does with it.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Iterable, Iterator

from custodian.ingest.sanitizer import flag_price_claim, sanitize
from custodian.ingest.taxonomy import Taxonomy, default_taxonomy
from custodian.ingest.text import find_price
from custodian.money import MoneyError, parse_paise
from custodian.schemas.catalog import CatalogItem, Sanitization

#: Every spelling of "we have this" seen in the source export.
_IN_STOCK: Final[frozenset[str]] = frozenset({"y", "yes", "1", "true", "in stock", "instock", "available"})


@dataclass(frozen=True, slots=True)
class LoadIssue:
    """Something ingest had to resolve, decide, or refuse."""

    sku: str
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"{self.sku}: {self.kind} — {self.detail}"


@dataclass
class LoadReport:
    """What ingest did, so the quality of the feed is inspectable."""

    rows_read: int = 0
    items_built: int = 0
    issues: list[LoadIssue] = field(default_factory=list)

    @property
    def skipped(self) -> int:
        return self.rows_read - self.items_built

    def of_kind(self, kind: str) -> list[LoadIssue]:
        return [issue for issue in self.issues if issue.kind == kind]

    def __str__(self) -> str:
        kinds = sorted({issue.kind for issue in self.issues})
        summary = ", ".join(f"{k}={len(self.of_kind(k))}" for k in kinds) or "no issues"
        return f"{self.items_built}/{self.rows_read} items built ({summary})"


def load_csv(
    path: Path | str, *, taxonomy: Taxonomy | None = None
) -> tuple[list[CatalogItem], LoadReport]:
    """Normalise a merchant CSV export into catalog items."""
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return load_rows(csv.DictReader(handle), taxonomy=taxonomy)


def load_rows(
    rows: Iterable[dict[str, str]], *, taxonomy: Taxonomy | None = None
) -> tuple[list[CatalogItem], LoadReport]:
    """Normalise already-parsed rows. Split out so tests need no file."""
    tax = taxonomy or default_taxonomy()
    report = LoadReport()
    items: list[CatalogItem] = []

    for row in rows:
        report.rows_read += 1
        if (built := _build_item(row, tax, report)) is not None:
            items.append(built)
            report.items_built += 1

    return items, report


def _build_item(row: dict[str, str], tax: Taxonomy, report: LoadReport) -> CatalogItem | None:
    sku = (row.get("sku") or "").strip()
    raw_name = (row.get("item_name") or "").strip()
    if not sku or not raw_name:
        report.issues.append(LoadIssue(sku or "<no sku>", "UNUSABLE_ROW", "missing sku or item name"))
        return None

    price = _resolve_price(sku, raw_name, row, report)
    if price is None:
        return None
    price_paise, embedded_price = price

    raw_description = (row.get("description") or "").strip()
    description = sanitize(raw_description)
    if not description.clean:
        report.issues.append(
            LoadIssue(sku, "SANITIZER_FLAG", f"{[str(f) for f in description.finding.flags]}")
        )

    finding: Sanitization = description.finding
    if embedded_price is not None and embedded_price != price_paise:
        report.issues.append(
            LoadIssue(sku, "PRICE_DISAGREEMENT",
                      f"name says {embedded_price} paise, price field says {price_paise}")
        )
        finding = flag_price_claim(finding)

    placement = tax.place(raw_name)
    if not placement.resolved:
        report.issues.append(LoadIssue(sku, "UNPLACED", f"no taxonomy entry for {placement.residue!r}"))

    measure = placement.measure
    return CatalogItem(
        item_id=sku,
        name=_display_name(raw_name),
        raw_name=raw_name,
        price_paise=price_paise,
        in_stock=(row.get("stock") or "").strip().lower() in _IN_STOCK,
        description=description.clean_text,
        raw_description=raw_description,
        base=placement.base,
        form=placement.form,
        category=placement.category,
        unit_quantity=measure.quantity if measure else None,
        unit=str(measure.unit) if measure else None,
        sanitization=finding,
    )


def _resolve_price(
    sku: str, raw_name: str, row: dict[str, str], report: LoadReport
) -> tuple[int, int | None] | None:
    """Resolve the price, returning it with any price found inside the name."""
    embedded = find_price(raw_name)
    embedded_paise = embedded[0] if embedded else None

    for column in ("price", "mrp"):
        text = (row.get(column) or "").strip()
        if not text:
            continue
        try:
            paise = parse_paise(text)
        except MoneyError:
            report.issues.append(LoadIssue(sku, "UNPARSEABLE_PRICE", f"{column}={text!r}"))
            continue
        if paise <= 0:
            continue
        if column == "mrp":
            report.issues.append(LoadIssue(sku, "PRICE_FROM_MRP", "price column empty; used mrp"))
        return paise, embedded_paise

    if embedded_paise is not None:
        report.issues.append(LoadIssue(sku, "PRICE_FROM_NAME", f"only price found was in the item name"))
        return embedded_paise, None  # no disagreement possible: it is the same number

    report.issues.append(LoadIssue(sku, "NO_PRICE", "item has no usable price and cannot be sold"))
    return None


def _display_name(raw_name: str) -> str:
    """The agent-facing name: price removed, whitespace tidied, casing left alone."""
    stripped = find_price(raw_name)
    return (stripped[1] if stripped else raw_name).strip() or raw_name
