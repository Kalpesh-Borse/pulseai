"""Cross-item theme clustering via embedding similarity, stored and queried through ChromaDB.

Two feedback items describing the same underlying problem in different words ("checkout is
slow" vs "payment page lags") share no keyword, so keyword/string grouping would treat them
as unrelated. Embedding each item's theme phrases and clustering by vector similarity catches
this. ChromaDB is the vector index that makes the nearest-neighbor lookups behind that
similarity check fast and reusable at scale — embeddings are still computed independently
(core/embeddings.py) and handed to ChromaDB, so this module also runs against a plain
in-memory/ephemeral client with a fake embedder in tests, with no external service required.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass

import chromadb

from config.settings import Settings
from core.embeddings import Embedder
from schemas.models import ClassifiedFeedback, ThemeCluster

_COLLECTION_NAME = "pulseai_theme_mentions"


@dataclass
class _ThemeMention:
    mention_id: str
    item_id: str
    theme_text: str
    quote: str


def _collect_mentions(items: list[ClassifiedFeedback]) -> list[_ThemeMention]:
    mentions: list[_ThemeMention] = []
    for item in items:
        themes = item.themes or [item.category.value.replace("_", " ")]
        for i, theme in enumerate(themes):
            mentions.append(
                _ThemeMention(
                    mention_id=f"{item.item_id}::{i}",
                    item_id=item.item_id,
                    theme_text=theme,
                    quote=item.text,
                )
            )
    return mentions


def _as_list(vector) -> list[float]:
    return vector.tolist() if hasattr(vector, "tolist") else list(vector)


def cluster_themes(
    items: list[ClassifiedFeedback],
    embedder: Embedder,
    settings: Settings,
    chroma_client: chromadb.ClientAPI | None = None,
) -> list[ThemeCluster]:
    mentions = _collect_mentions(items)
    if not mentions:
        return []

    vectors = embedder.embed([m.theme_text for m in mentions])

    client = chroma_client or chromadb.EphemeralClient()
    try:
        client.delete_collection(_COLLECTION_NAME)
    except Exception:  # noqa: BLE001 — collection may not exist yet, that's fine
        pass
    collection = client.create_collection(name=_COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    collection.add(
        ids=[m.mention_id for m in mentions],
        embeddings=[_as_list(v) for v in vectors],
        documents=[m.theme_text for m in mentions],
    )

    cluster_of: dict[str, int] = {}
    cluster_members: dict[int, list[_ThemeMention]] = defaultdict(list)
    next_cluster_id = 0

    for mention, vector in zip(mentions, vectors):
        if mention.mention_id in cluster_of:
            continue

        # Query the FULL collection, not just a fixed top-K: an approximate top-K cutoff can
        # tie-break away an already-clustered neighbor once a true cluster exceeds K members,
        # silently fragmenting one cluster into several. Batches here are small enough
        # (dozens-hundreds of mentions) that an exhaustive query per mention is cheap.
        results = collection.query(
            query_embeddings=[_as_list(vector)],
            n_results=len(mentions),
        )
        neighbor_ids = results["ids"][0]
        neighbor_distances = results["distances"][0]

        assigned_cluster = None
        for neighbor_id, distance in zip(neighbor_ids, neighbor_distances):
            if neighbor_id == mention.mention_id:
                continue
            if neighbor_id in cluster_of and distance <= settings.theme_cluster_distance_threshold:
                assigned_cluster = cluster_of[neighbor_id]
                break

        if assigned_cluster is None:
            assigned_cluster = next_cluster_id
            next_cluster_id += 1

        cluster_of[mention.mention_id] = assigned_cluster
        cluster_members[assigned_cluster].append(mention)

    clusters: list[ThemeCluster] = []
    for cluster_id, members in cluster_members.items():
        label = Counter(m.theme_text for m in members).most_common(1)[0][0]
        item_ids = sorted({m.item_id for m in members})

        quotes: list[str] = []
        seen_quotes: set[str] = set()
        for m in members:
            if m.quote not in seen_quotes:
                quotes.append(m.quote)
                seen_quotes.add(m.quote)
            if len(quotes) == 3:
                break

        clusters.append(
            ThemeCluster(
                cluster_id=f"cluster_{cluster_id}",
                label=label,
                item_ids=item_ids,
                count=len(item_ids),
                example_quotes=quotes,
            )
        )

    clusters.sort(key=lambda c: c.count, reverse=True)
    return clusters
