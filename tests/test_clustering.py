import numpy as np

from config.settings import Settings
from core.clustering import cluster_themes
from schemas.models import Category, ClassifiedFeedback, Sentiment, SentimentLabel, UrgencyLevel

# Fixed, hand-picked unit vectors so clustering behavior is fully deterministic in tests —
# no real ML model is loaded. "invoice duplicate charge" is nearly parallel to
# "billing double charge" (same underlying theme, different wording); "export timeout" and
# "unrelated theme" are orthogonal to everything.
_VECTORS = {
    "export timeout": [1.0, 0.0, 0.0],
    "billing double charge": [0.0, 1.0, 0.0],
    "invoice duplicate charge": [0.0, 0.99, 0.14],
    "unrelated theme": [0.0, 0.0, 1.0],
}


class FakeEmbedder:
    def embed(self, texts: list[str]) -> np.ndarray:
        return np.array([_VECTORS[t] for t in texts])


def _item(item_id: str, theme: str, text: str) -> ClassifiedFeedback:
    return ClassifiedFeedback(
        item_id=item_id,
        text=text,
        category=Category.OTHER,
        sentiment=Sentiment(label=SentimentLabel.NEGATIVE, score=-0.5),
        urgency=UrgencyLevel.MEDIUM,
        themes=[theme],
        reasoning="test",
    )


def test_near_duplicate_themes_worded_differently_cluster_together():
    items = [
        _item("A1", "export timeout", "Export keeps timing out."),
        _item("A2", "export timeout", "Same export timeout again."),
        _item("B1", "billing double charge", "Charged twice this month."),
        _item("B2", "invoice duplicate charge", "Invoice shows a duplicate line item."),
    ]

    clusters = cluster_themes(items, FakeEmbedder(), Settings())

    assert len(clusters) == 2
    by_label = {c.label: c for c in clusters}
    assert set(by_label["export timeout"].item_ids) == {"A1", "A2"}
    billing_cluster = by_label.get("billing double charge") or by_label.get("invoice duplicate charge")
    assert set(billing_cluster.item_ids) == {"B1", "B2"}


def test_unrelated_theme_forms_its_own_singleton_cluster():
    items = [
        _item("A1", "export timeout", "Export keeps timing out."),
        _item("C1", "unrelated theme", "Something completely different."),
    ]

    clusters = cluster_themes(items, FakeEmbedder(), Settings())

    assert len(clusters) == 2
    assert all(c.count == 1 for c in clusters)


def test_empty_input_returns_no_clusters():
    assert cluster_themes([], FakeEmbedder(), Settings()) == []


def test_large_identical_theme_group_stays_one_cluster():
    # Regression test: a naive top-K nearest-neighbor query (K < group size) can tie-break
    # away an already-clustered neighbor once a true cluster exceeds K members, silently
    # fragmenting one cluster into several. This must stay a single cluster of 25.
    items = [_item(f"A{i}", "export timeout", f"text {i}") for i in range(25)]

    clusters = cluster_themes(items, FakeEmbedder(), Settings())

    assert len(clusters) == 1
    assert clusters[0].count == 25


def test_clusters_sorted_by_size_descending():
    items = [
        _item("A1", "export timeout", "t1"),
        _item("A2", "export timeout", "t2"),
        _item("A3", "export timeout", "t3"),
        _item("C1", "unrelated theme", "t4"),
    ]

    clusters = cluster_themes(items, FakeEmbedder(), Settings())

    assert clusters[0].count == 3
    assert clusters[0].label == "export timeout"
