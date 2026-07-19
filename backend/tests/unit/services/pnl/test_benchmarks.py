"""Unit tests for P&L benchmark grading and Toast discount extraction.

Both are pure functions over in-memory data — no DB, so these run with
--noconftest (the shared conftest drops the schema, which is dangerous when
DATABASE_URL points at production).
"""
import os
from decimal import Decimal

# sync_service pulls in app.core.config, whose Settings requires real values at
# import time. These are never used — nothing here opens a connection or signs a
# token — but they have to exist for the module to import under --noconftest.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test/test")
os.environ.setdefault("JWT_PRIVATE_KEY", "test")
os.environ.setdefault("JWT_PUBLIC_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")
os.environ.setdefault("ENCRYPTION_KEY", "test")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("STORAGE_BUCKET", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

from app.schemas.pnl import PnLLineItems  # noqa: E402
from app.services.pnl.calculator import _benchmark_chips  # noqa: E402
from app.services.toast.sync_service import (  # noqa: E402
    _sum_applied_discounts,
    iter_applied_discounts,
)


def _chips(**pcts):
    li = PnLLineItems(**{k: Decimal(str(v)) for k, v in pcts.items()})
    return {c.metric: c for c in _benchmark_chips(li)}


# ---- benchmark grading (cost ratios: lower is better) ----

def test_food_cost_within_target_is_good():
    assert _chips(cogs_pct=32)["cogs_pct"].status == "good"


def test_food_cost_slightly_over_is_watch():
    assert _chips(cogs_pct=36)["cogs_pct"].status == "watch"


def test_food_cost_far_over_is_bad():
    # June 2026 actual — 48.1% against a 28-34% target.
    chip = _chips(cogs_pct=48.1)["cogs_pct"]
    assert chip.status == "bad"
    assert chip.value_pct == Decimal("48.1")


def test_labor_and_prime_graded_independently():
    chips = _chips(labor_pct=13.8, prime_cost_pct=61.9)
    assert chips["labor_pct"].status == "good"
    assert chips["prime_cost_pct"].status == "watch"


def test_net_profit_inverts_higher_is_better():
    assert _chips(net_profit_pct=12)["net_profit_pct"].status == "good"
    assert _chips(net_profit_pct=6)["net_profit_pct"].status == "watch"
    assert _chips(net_profit_pct=4.2)["net_profit_pct"].status == "bad"


def test_missing_metric_is_unknown_not_zero():
    # A period with no revenue must not grade as a catastrophic 0% — it has no
    # data, which is a different statement from "performed badly".
    chip = _chips()["cogs_pct"]
    assert chip.status == "unknown"
    assert chip.value_pct is None


# ---- discount extraction ----

def _order(check_discounts=None, selection_discounts=None):
    return {
        "guid": "order-1",
        "checks": [
            {
                "appliedDiscounts": check_discounts or [],
                "selections": [{"appliedDiscounts": selection_discounts or []}],
            }
        ],
    }


def test_extracts_check_level_discount_with_name():
    raw = _order(check_discounts=[
        {"guid": "d1", "name": "50% Staff Discount", "discountAmount": 12.5, "discountType": "PERCENT"},
    ])
    out = list(iter_applied_discounts(raw))
    assert len(out) == 1
    assert out[0]["name"] == "50% Staff Discount"
    assert out[0]["amount"] == Decimal("12.5")
    assert out[0]["scope"] == "check"
    assert out[0]["discount_type"] == "PERCENT"


def test_extracts_selection_level_discount_as_item_scope():
    raw = _order(selection_discounts=[
        {"guid": "d2", "name": "15% Off Student's Promo", "discountAmount": 3.75},
    ])
    out = list(iter_applied_discounts(raw))
    assert out[0]["scope"] == "item"
    assert out[0]["name"] == "15% Off Student's Promo"


def test_name_falls_back_to_nested_discount_object():
    raw = _order(check_discounts=[
        {"guid": "d3", "discount": {"name": "100% HQ Meal"}, "discountAmount": 9.99},
    ])
    assert list(iter_applied_discounts(raw))[0]["name"] == "100% HQ Meal"


def test_unnamed_discount_gets_placeholder_not_dropped():
    raw = _order(check_discounts=[{"guid": "d4", "discountAmount": 5}])
    out = list(iter_applied_discounts(raw))
    assert out[0]["name"] == "(unnamed discount)"


def test_discount_without_amount_is_skipped():
    raw = _order(check_discounts=[{"guid": "d5", "name": "Zero value"}])
    assert list(iter_applied_discounts(raw)) == []


def test_missing_guid_falls_back_to_positional_key():
    # Without a stable guid, two discounts on one order would collide on the
    # (tenant_id, toast_guid) unique constraint and silently overwrite.
    raw = _order(check_discounts=[
        {"name": "A", "discountAmount": 1},
        {"name": "B", "discountAmount": 2},
    ])
    guids = [d["guid"] for d in iter_applied_discounts(raw)]
    assert len(set(guids)) == 2


def test_sum_matches_iteration_total():
    # The order-level aggregate and the per-discount rows must agree, or the
    # breakdown won't reconcile to the P&L's discount line.
    raw = _order(
        check_discounts=[{"guid": "a", "name": "A", "discountAmount": 10}],
        selection_discounts=[{"guid": "b", "name": "B", "discountAmount": 2.5}],
    )
    assert _sum_applied_discounts(raw) == sum(d["amount"] for d in iter_applied_discounts(raw))


def test_sum_returns_none_when_no_discounts():
    assert _sum_applied_discounts(_order()) is None
