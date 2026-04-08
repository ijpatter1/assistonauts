"""Hybrid retrieval — vector similarity + FTS keyword search with RRF."""

from __future__ import annotations

from dataclasses import dataclass

from assistonauts.archivist.database import ArchivistDB


@dataclass
class HybridResult:
    """A single hybrid search result with fused score."""

    path: str
    score: float


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    k: int = 60,
    relevance_floor: float = 0.0,
) -> list[HybridResult]:
    """Combine multiple ranked result lists using Reciprocal Rank Fusion.

    RRF score for document d = sum over all lists of 1 / (k + rank_in_list).
    Higher k dampens the effect of rank differences.

    Args:
        ranked_lists: Each list is a ranked sequence of article paths.
        k: RRF constant (default 60, per the original paper).
        relevance_floor: Minimum score to include in results.

    Returns:
        Fused results sorted by descending score.
    """
    scores: dict[str, float] = {}
    for ranked_list in ranked_lists:
        for rank, path in enumerate(ranked_list):
            scores[path] = scores.get(path, 0.0) + 1.0 / (k + rank + 1)

    results = [
        HybridResult(path=path, score=score)
        for path, score in scores.items()
        if score >= relevance_floor
    ]
    results.sort(key=lambda r: r.score, reverse=True)
    return results


def hybrid_search(
    db: ArchivistDB,
    query: str,
    query_embedding: list[float],
    limit: int = 20,
    fts_limit: int = 50,
    vec_limit: int = 50,
    rrf_k: int = 60,
    relevance_floor: float = 0.0,
) -> list[HybridResult]:
    """Hybrid search combining FTS keyword search and vector similarity.

    Runs both searches independently, then fuses results with RRF.
    No arbitrary result cap — relevance floor filters low-quality matches.

    Args:
        db: The Archivist database to search.
        query: Text query for FTS search.
        query_embedding: Vector embedding of the query for similarity search.
        limit: Maximum results to return after fusion.
        fts_limit: Max results from FTS search.
        vec_limit: Max results from vector search.
        rrf_k: RRF constant.
        relevance_floor: Minimum fused score to include.

    Returns:
        Fused results sorted by relevance.
    """
    # FTS search
    fts_results = db.search_fts(query, limit=fts_limit)
    fts_ranked = [str(r["path"]) for r in fts_results]

    # Vector search
    vec_results = db.search_vec(query_embedding, limit=vec_limit)
    vec_ranked = [str(r["path"]) for r in vec_results]

    # Fuse with RRF
    ranked_lists: list[list[str]] = []
    if fts_ranked:
        ranked_lists.append(fts_ranked)
    if vec_ranked:
        ranked_lists.append(vec_ranked)

    if not ranked_lists:
        return []

    fused = reciprocal_rank_fusion(
        ranked_lists, k=rrf_k, relevance_floor=relevance_floor
    )
    return fused[:limit]
