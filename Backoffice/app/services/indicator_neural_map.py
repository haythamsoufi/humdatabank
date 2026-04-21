"""
Build 2D/3D scatter data for Indicator Bank embedding visualization.

High-dimensional embeddings are projected via PCA (fast) or t-SNE
(better clusters). Each node carries projected coordinates, metadata,
and pre-computed nearest neighbors for on-demand edge drawing.
"""

import logging
import numpy as np
from typing import Any, Dict, List, Optional, Tuple

from app.extensions import db
from app.models import IndicatorBank, IndicatorBankEmbedding
from app.models import Sector
from app.models.indicator_bank import SubSector

logger = logging.getLogger(__name__)

DEFAULT_MAX_NODES = 5000
DEFAULT_NEIGHBORS = 8


def _embedding_to_array(emb: Any) -> Optional[np.ndarray]:
    if emb is None:
        return None
    if isinstance(emb, np.ndarray):
        return emb.astype(np.float32)
    if hasattr(emb, "tolist"):
        return np.array(emb.tolist(), dtype=np.float32)
    return np.array(list(emb), dtype=np.float32)


def _project_pca(matrix: np.ndarray, n_components: int = 3) -> np.ndarray:
    """PCA projection (mean-centered, top-k singular vectors)."""
    centered = matrix - matrix.mean(axis=0)
    U, S, Vt = np.linalg.svd(centered, full_matrices=False)
    return centered @ Vt[:n_components].T


def _project_tsne(matrix: np.ndarray, n_components: int = 3, perplexity: float = 30.0) -> np.ndarray:
    """t-SNE projection via sklearn."""
    try:
        from sklearn.manifold import TSNE
        perp = min(perplexity, max(5.0, len(matrix) / 4.0))
        tsne = TSNE(n_components=n_components, perplexity=perp, random_state=42,
                     init="pca" if n_components <= 3 else "random",
                     learning_rate="auto")
        return tsne.fit_transform(matrix)
    except ImportError:
        logger.warning("sklearn not available, falling back to PCA")
        return _project_pca(matrix, n_components)


def _load_records(max_nodes: int, exclude_archived: bool):
    """Load indicator embedding records from the database."""
    q = (
        db.session.query(IndicatorBankEmbedding, IndicatorBank)
        .join(IndicatorBank, IndicatorBankEmbedding.indicator_bank_id == IndicatorBank.id)
        .order_by(IndicatorBank.name)
    )
    if exclude_archived:
        q = q.filter(IndicatorBank.archived == False)  # noqa: E712
    rows = q.limit(max_nodes + 50).all()

    seen_ids = set()
    records: List[Tuple[IndicatorBankEmbedding, IndicatorBank]] = []
    for emb, ind in rows:
        if ind.id in seen_ids:
            continue
        seen_ids.add(ind.id)
        records.append((emb, ind))
        if len(records) >= max_nodes:
            break
    return records


def _build_matrix(records):
    """Build (n, dims) embedding matrix from records."""
    n = len(records)
    first_vec = _embedding_to_array(records[0][0].embedding)
    matrix = np.zeros((n, len(first_vec)), dtype=np.float32)
    for i, (emb, _) in enumerate(records):
        vec = _embedding_to_array(emb.embedding)
        if vec is not None:
            matrix[i] = vec
    return matrix


def _normalize_coords(coords: np.ndarray, scale: float = 100.0) -> np.ndarray:
    """Center and scale coordinates to [-scale, scale]."""
    centered = coords - coords.mean(axis=0)
    max_abs = np.abs(centered).max()
    if max_abs > 0:
        centered = centered / max_abs * scale
    return centered


def _lookup_sectors(records):
    """Batch-load sector and sub-sector names for all indicators."""
    sector_ids = set()
    sub_sector_ids = set()
    for _, ind in records:
        for level in ("primary", "secondary", "tertiary"):
            sid = (ind.sector or {}).get(level)
            if sid:
                sector_ids.add(sid)
            ssid = (ind.sub_sector or {}).get(level)
            if ssid:
                sub_sector_ids.add(ssid)
    sectors = {}
    if sector_ids:
        for s in Sector.query.filter(Sector.id.in_(sector_ids)).all():
            sectors[s.id] = s.name or str(s.id)
    sub_sectors = {}
    if sub_sector_ids:
        for ss in SubSector.query.filter(SubSector.id.in_(sub_sector_ids)).all():
            sub_sectors[ss.id] = ss.name or str(ss.id)
    return sectors, sub_sectors


def build_embedding_scatter(
    max_nodes: int = DEFAULT_MAX_NODES,
    n_neighbors: int = DEFAULT_NEIGHBORS,
    method: str = "pca",
    dimensions: int = 3,
    exclude_archived: bool = True,
) -> Dict:
    """
    Build scatter payload with 2D or 3D positions + per-node neighbors.

    Returns dict with: nodes, groups, count.
    Each node: id, label, x, y, z (if 3D), group, sector, unit, definition, neighbors.
    """
    records = _load_records(max_nodes, exclude_archived)
    if not records:
        return {"nodes": [], "groups": [], "count": 0}

    n = len(records)
    dims = max(2, min(3, dimensions))
    matrix = _build_matrix(records)

    if method == "tsne" and n >= 5:
        coords = _project_tsne(matrix, n_components=dims)
    else:
        coords = _project_pca(matrix, n_components=dims)

    coords = _normalize_coords(coords, scale=100.0)

    # Cosine similarity matrix
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normed = matrix / norms
    sim_matrix = normed @ normed.T

    sectors, sub_sectors = _lookup_sectors(records)
    id_list = [ind.id for _, ind in records]

    group_set = set()
    nodes: List[Dict] = []
    for i, (emb, ind) in enumerate(records):
        group = (ind.type or "other").strip() or "other"
        group_set.add(group)
        primary_sector_id = (ind.sector or {}).get("primary")
        sector_name = sectors.get(primary_sector_id, "") if primary_sector_id else ""
        primary_subsector_id = (ind.sub_sector or {}).get("primary")
        subsector_name = sub_sectors.get(primary_subsector_id, "") if primary_subsector_id else ""

        programs_raw = (ind.related_programs or "").strip()
        program = programs_raw.split(",")[0].strip() if programs_raw else ""

        sims = sim_matrix[i].copy()
        sims[i] = -1
        top_idx = np.argsort(sims)[::-1][:n_neighbors]
        neighbors = []
        for j in top_idx:
            s = float(sims[j])
            if s > 0:
                neighbors.append({"id": int(id_list[j]), "similarity": round(s, 3)})

        defn = (ind.definition or "").replace("\n", " ").strip()
        node = {
            "id": ind.id,
            "label": (ind.name or str(ind.id)),
            "x": round(float(coords[i, 0]), 2),
            "y": round(float(coords[i, 1]), 2),
            "group": group,
            "sector": sector_name,
            "sub_sector": subsector_name,
            "unit": ind.unit or "",
            "program": program,
            "emergency": bool(ind.emergency),
            "kpi_code": ind.fdrs_kpi_code or "",
            "definition": defn,
            "neighbors": neighbors,
        }
        if dims >= 3:
            node["z"] = round(float(coords[i, 2]), 2)
        nodes.append(node)

    return {
        "nodes": nodes,
        "groups": sorted(group_set),
        "count": len(nodes),
    }


def probe_query_embedding(
    query: str,
    top_k: int = 10,
    max_nodes: int = DEFAULT_MAX_NODES,
    exclude_archived: bool = True,
) -> Dict:
    """
    Embed a free-text query and return its cosine similarity to all
    indicator embeddings, plus the top-K nearest indicator IDs.

    The frontend positions the probe marker as a weighted centroid
    of the nearest neighbours that are already rendered on-screen.
    """
    from app.services.ai_embedding_service import AIEmbeddingService

    records = _load_records(max_nodes, exclude_archived)
    if not records:
        return {"neighbors": [], "cost": 0}

    svc = AIEmbeddingService()
    query_vec, cost = svc.generate_embedding(query)
    q = np.array(query_vec, dtype=np.float32)

    matrix = _build_matrix(records)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normed = matrix / norms

    q_norm = np.linalg.norm(q)
    if q_norm > 0:
        q = q / q_norm
    sims = normed @ q

    id_list = [ind.id for _, ind in records]
    top_idx = np.argsort(sims)[::-1][:top_k]
    neighbors = []
    for j in top_idx:
        s = float(sims[j])
        if s > 0:
            neighbors.append({"id": int(id_list[j]), "similarity": round(s, 4)})

    return {"neighbors": neighbors, "cost": round(cost, 6)}
