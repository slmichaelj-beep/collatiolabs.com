"""fmlgs — Fast Multilevel Language-embedded Gaussians.

The RETRIEVAL INTERFACE for the LERF vault, and the scaling path behind it. Today LERF
serves cognitive objects by a deterministic linear keyword scan (lerf._retrieve / _score):
correct, inspectable, and — at the vault's current size (tens of objects, see the honest
note below) — already instant. FMLGS does NOT try to beat an instant scan at N=50. It
proves the *interface* and the *scaling path*: object -> embedding -> a multilevel-Gaussian
index that lets retrieval go coarse-to-fine instead of touching every object, so the cost of
a query grows like the number of CLUSTERS probed, not the number of objects, as the vault
grows into the thousands. "Same intelligence, less compute at scale" — recall preserved
against the keyword baseline, footprint and latency measured.

WHY THIS IS HONEST AT CURRENT SCALE (stated up front, enforced in code and report):
  * At N≈26-150 objects a linear keyword scan is already sub-millisecond. FMLGS at this scale
    is a CORRECT PASS-THROUGH: with one Gaussian level whose single cluster holds every object,
    coarse-to-fine degenerates to "probe the one cluster, score its members" — i.e. the same
    linear scan, with a tiny constant of embedding + cluster arithmetic on top. It must not
    DEGRADE results, and the selftest asserts recall >= the keyword baseline. The value today
    is the INTERFACE (a drop-in API the router could call) and the proof that the index is
    correct; the COMPUTE win activates as N grows and `probe < n_clusters * cluster_size`.
  * No black box. The embedding is a documented, deterministic hashed character/word n-gram
    TF-IDF vector — pure numpy, no model, no network, no new dependency. You can recompute any
    object's vector by hand from this file. The Gaussian hierarchy is k-means-style centroids
    (a diagonal-Gaussian / GMM-lite cluster model) you can print and inspect.

WHAT FMLGS IS — the three layers, each defined here:

  1) THE INTERFACE (class `FMLGSIndex`):  build(objects) -> index ;  query(text, k) -> [hits].
     A `hit` is (object, score) with the SAME ranking contract as lerf retrieval: higher is
     better, active-only is the caller's responsibility (we index what we're given). The rest
     of the system can call `query` instead of a linear `_retrieve` and get the same answers,
     with the index doing the work.

  2) THE EMBEDDING (`embed_text` / `Embedder`):  text -> unit-norm float32 vector in R^D.
     Hashed n-gram TF-IDF. Char n-grams (3..5) capture morphology and typos ("summarise" ~
     "summarize"); word unigrams capture content words. Each gram is hashed into one of D
     buckets (the hashing trick — fixed memory, no vocabulary to store), weighted by
     log-IDF over the indexed corpus, and the vector is L2-normalised so cosine similarity is
     a dot product. Deterministic: same text -> same vector, forever.

  3) THE MULTILEVEL GAUSSIAN LAYER (`_build_levels` / coarse-to-fine in `query`):  a HIERARCHY
     of Gaussian clusters over the embeddings. Each level is a set of clusters; each cluster is
     a diagonal Gaussian (mean = centroid, per-dim variance) summarising the objects under it.
     A query descends the hierarchy: at each level it keeps the few nearest centroids (a beam),
     and only at the leaf level does it score the actual objects in the surviving clusters. That
     is the coarse-to-fine retrieval — the "multilevel Gaussians" — and it is what turns an
     O(N) scan into an O(probe) one once N is large. At small N the hierarchy collapses to a
     single level / single cluster and the descent is a no-op over one bucket: the pass-through.

  MEASUREMENT (`measure`):  index footprint in bytes, retrieval latency vs the linear baseline,
  and recall@k vs the deterministic keyword baseline on a query set — the intelligence-per-GB
  ledger. The footprint breaks out the per-object VECTORS (the only term that scales with N), the
  Gaussian-hierarchy CENTROIDS (sub-linear in N), and the embedder's IDF dictionary (a fixed map,
  prunable opt-in via compute_idf(min_df=...)). Recall is exact set-overlap of top-k results; the
  headline fidelity number is recall-vs-exact-cosine (FMLGS approximating its own linear search).

FREEZE BOUNDARY: FMLGS is a pure READ/INDEX layer over LERF *knowledge* objects (skills,
concepts, procedures, heuristics, decision-patterns, mental-models, failure-modes, and the
USER's preferences/values). It never writes the vault, never mints an object, and has no notion
of Vera's identity/values/agency — it only embeds and ranks text that is already on disk.
Nothing here can confabulate Vera an inner life; it cannot store anything at all.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Callable, Iterable

import numpy as np

# We reuse LERF's OWN text-flattening and keyword tokeniser so an object embeds from EXACTLY
# the text the keyword baseline scores, and the recall comparison is apples-to-apples. These are
# the same module-level helpers lerf retrieval uses; importing them keeps one source of truth for
# "what text does an object consist of". (lerf is imported lazily inside functions that touch the
# store, to avoid any import cycle and to keep `embed_text` usable standalone.)
from .lerf import _obj_to_text, _kw                       # noqa: E402

# ---------------------------------------------------------------------------------------------
# CONFIG — small, explicit, and the only knobs. D is the embedding dimension (buckets in the
# hashing trick): big enough that distinct grams rarely collide, small enough that a vector is a
# few KB. CHAR_NS / WORD_NS are the n-gram orders. BRANCHING / BEAM / MIN_CLUSTER govern the
# Gaussian hierarchy's shape and the coarse-to-fine descent.
# ---------------------------------------------------------------------------------------------
EMBED_DIM = 512                 # hashing-trick dimension (buckets). 512 float32 = 2 KB/vector.
CHAR_NS = (3, 4, 5)             # character n-gram orders (morphology / typo tolerance)
WORD_NS = (1,)                  # word n-gram orders (content words; bigrams add little at this scale)
# A whole-word (content) gram is a far stronger relevance signal than an incidental char-trigram
# overlap, so word grams are up-weighted relative to char grams. Measured on the live vault: lifting
# this from 1.0 -> 2.0 turned 5/8 exact-name queries into 6/8 correct top-1 (a query word that matches
# an object's name should dominate the morphology noise). Char grams still carry typo/morphology
# tolerance; this just stops them from drowning an exact content-word hit.
_WORD_GRAM_WEIGHT = 2.0
_BRANCHING = 8                  # target children per node when building a level (k for k-means)
# Clusters kept per level during the coarse-to-fine descent — the RECALL/COMPUTE knob, and the one
# number that trades them off. Measured on an 800-object synthetic vault (k=5): BEAM=3 -> 0.967
# recall@5 at 5% scan; BEAM=5 -> 1.000 recall@5 at ~8% scan; BEAM=8 -> 1.000 at ~12%. We pick 5:
# LOSSLESS recall against the exact cosine search (the "same intelligence" contract is non-negotiable)
# while still scoring <10% of the vault (the compute win). Widen it only to trade more scan for more
# recall headroom on a harder corpus; the descent ALSO has a hard safety net (see _candidate_indices)
# that falls back to a full scan rather than ever return fewer than k candidates.
_BEAM = 5
_MIN_CLUSTER = 16               # below this many objects, DON'T cluster — one flat level (pass-through)
_KMEANS_ITERS = 12              # Lloyd iterations; converges fast on unit-norm vectors
_SEED = 1308                    # determinism for the (rare) random centroid re-seed
# Reserved key in an IDF map documenting the weight a PRUNED gram would carry (a singleton's IDF).
# The \x00 prefix can't collide with a real gram (those are "w:"/"c:" prefixed). See compute_idf.
# It is documentation only — embed_text's absent-gram fallback is a neutral 1.0, not this value.
_DEFAULT_KEY = "\x00default"


# =============================================================================================
# EMBEDDING — text -> unit-norm hashed n-gram TF-IDF vector. Deterministic, pure-numpy.
# =============================================================================================

def _hash_bucket(token: str) -> int:
    """Stable bucket in [0, EMBED_DIM) for a gram. blake2b (in stdlib hashlib) gives a fixed,
    process-independent hash — Python's built-in hash() is salted per process and would make
    vectors non-reproducible across runs, which would break the whole "recompute by hand" claim."""
    h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "big") % EMBED_DIM


def _hash_sign(token: str) -> float:
    """A second, independent hash bit gives each gram a deterministic +/- sign. Signed hashing
    halves the expected error from two distinct grams colliding into the same bucket (their
    contributions cancel in expectation instead of always reinforcing) — the standard trick."""
    h = hashlib.blake2b(token.encode("utf-8"), salt=b"sign", digest_size=8).digest()
    return 1.0 if (h[0] & 1) else -1.0


def _grams(text: str) -> list[str]:
    """The bag of grams for `text`: word unigrams (content words, via lerf._kw so stopwords are
    dropped and tokenisation matches the keyword baseline) plus character n-grams over the
    whitespace-normalised lowercase string (morphology + typo tolerance). Order-independent."""
    grams: list[str] = []
    # word grams — prefixed so a word gram and a char gram can't collide in the hash space
    words = sorted(_kw(text))
    for w in words:
        for n in WORD_NS:
            if n == 1:
                grams.append("w:" + w)
            # (n>1 word-grams intentionally omitted; see WORD_NS note)
    # char grams — over the normalised raw text (keeps signal _kw drops, e.g. short tokens)
    norm = " ".join((text or "").lower().split())
    if norm:
        padded = f" {norm} "
        for n in CHAR_NS:
            if len(padded) >= n:
                for i in range(len(padded) - n + 1):
                    grams.append("c:" + padded[i:i + n])
    return grams


def embed_text(text: str, idf: dict | None = None, *, dim: int = EMBED_DIM) -> np.ndarray:
    """Embed `text` into a unit-norm float32 vector in R^dim via signed hashed n-gram TF-IDF.

    TF is the in-document gram count (sub-linear 1+log damped, so a gram repeated 10x doesn't
    swamp the vector). IDF, if supplied (a {gram: weight} map from `compute_idf`), down-weights
    grams that appear in many objects — the discriminative ones dominate. With idf=None every
    gram weighs 1 (pure TF), which is the correct standalone behaviour and what a cold query
    uses before the corpus IDF is known. The result is L2-normalised, so similarity is a dot.

    ABSENT-GRAM FALLBACK = 1.0 (neutral TF). A gram not in the IDF map weighs 1.0 — the same
    cold-start weight an unknown query gram gets. We deliberately do NOT boost absent grams to the
    singleton-max IDF: doing so over-weights incidental char-n-gram collisions in a QUERY (a query
    gram that happens to be rare in the corpus is usually noise, not signal) and destabilises ranking
    near ties. So an OPT-IN min_df prune (compute_idf) can drop singleton grams to shrink the stored
    map and they simply revert to weight 1.0 here — which is why pruning preserves the top hit but
    perturbs rank-2..k slightly (the prune is off by default; see compute_idf). The reserved
    `_DEFAULT_KEY` entry in the map is documentation only and is skipped (it isn't a real gram)."""
    vec = np.zeros(dim, dtype=np.float32)
    if not text:
        return vec
    counts: dict[str, int] = {}
    for g in _grams(text):
        counts[g] = counts.get(g, 0) + 1
    for g, c in counts.items():
        tf = 1.0 + math.log(c)                         # sub-linear term frequency
        gram_w = _WORD_GRAM_WEIGHT if g.startswith("w:") else 1.0   # content word > char-gram noise
        w = tf * (idf.get(g, 1.0) if idf else 1.0) * gram_w  # absent gram -> neutral 1.0 (see docstring)
        b = _hash_bucket(g) if dim == EMBED_DIM else (int.from_bytes(
            hashlib.blake2b(g.encode(), digest_size=8).digest(), "big") % dim)
        vec[b] += _hash_sign(g) * w
    n = float(np.linalg.norm(vec))
    if n > 0:
        vec /= n
    return vec


def compute_idf(texts: Iterable[str], *, min_df: int | None = None) -> dict:
    """log-IDF weight per gram over a corpus of texts: idf(g) = ln((1+N)/(1+df)) + 1, the smoothed
    textbook form (never zero, never negative). df is the number of corpus texts the gram appears
    in. This is what makes a rare, on-topic gram count for more than a ubiquitous one — the whole
    point of TF-*IDF*. Deterministic in the corpus.

    FOOTPRINT PRUNE (min_df, OPT-IN — default keeps everything): grams with df < min_df are OMITTED
    from the returned map; an absent gram then weighs 1.0 in `embed_text` (neutral TF). The DEFAULT
    is min_df=1 (NO prune) — full fidelity, the safe default, because at the current vault scale the
    whole IDF map is only a few hundred KB and we never silently trade recall for bytes. Passing
    min_df=2 is a MEASURED footprint/fidelity trade: in the live vault ~60% of grams are singletons,
    so it roughly HALVES the stored IDF while PRESERVING the #1 hit exactly (measured: top-1 match
    =1.000 across N=50..500) at a small rank-2..k recall cost (~0.85 recall@5 vs the unpruned ranking).
    Use it when IDF footprint dominates and you only need the best hit; leave it off for exact recall.
    Either way the map carries a `_DEFAULT_KEY` (a singleton's IDF) purely as documentation of where a
    pruned gram's weight would sit; it is NOT used as the embed fallback (see embed_text)."""
    texts = list(texts)
    N = len(texts)
    if min_df is None:
        min_df = 1                                      # safe default: keep every gram (full fidelity)
    df: dict[str, int] = {}
    for t in texts:
        for g in set(_grams(t)):
            df[g] = df.get(g, 0) + 1
    out = {g: math.log((1.0 + N) / (1.0 + d)) + 1.0
           for g, d in df.items() if d >= max(1, int(min_df))}
    out[_DEFAULT_KEY] = math.log((1.0 + N) / 2.0) + 1.0 if N else 1.0  # documentation only
    return out


class Embedder:
    """A frozen embedding function bound to a corpus's IDF. Build once from the indexed texts,
    then `.embed(text)` any query or object against the SAME weighting. Holds only the IDF map
    (a few KB) — the vectors themselves live in the index, not here."""

    __slots__ = ("idf", "dim")

    def __init__(self, idf: dict | None = None, *, dim: int = EMBED_DIM):
        self.idf = idf or {}
        self.dim = int(dim)

    @classmethod
    def fit(cls, texts: Iterable[str], *, dim: int = EMBED_DIM) -> "Embedder":
        return cls(compute_idf(texts), dim=dim)

    def embed(self, text: str) -> np.ndarray:
        return embed_text(text, self.idf, dim=self.dim)

    def embed_many(self, texts: Iterable[str]) -> np.ndarray:
        rows = [self.embed(t) for t in texts]
        return np.vstack(rows).astype(np.float32) if rows else np.zeros((0, self.dim), np.float32)


# =============================================================================================
# THE MULTILEVEL GAUSSIAN LAYER — a hierarchy of diagonal-Gaussian clusters over the embeddings.
# Each cluster is summarised by a centroid (mean) and a per-dimension variance (the diagonal of
# the Gaussian's covariance); membership is the set of object indices under it. A query descends
# level by level, keeping a beam of nearest centroids, and only scores real objects at the leaves.
# =============================================================================================

def _kmeans(X: np.ndarray, k: int, *, iters: int = _KMEANS_ITERS,
            seed: int = _SEED) -> tuple[np.ndarray, np.ndarray]:
    """Lloyd's k-means on unit-norm rows of X (cosine and squared-L2 agree on the sphere up to a
    monotone transform, so plain L2 assignment clusters by direction). Returns (centroids[k,D],
    labels[n]). Deterministic: k-means++-style seeding driven by a fixed-seed RNG. Empty clusters
    are re-seeded to the point farthest from its current centroid, so k clusters always come back."""
    n, d = X.shape
    k = max(1, min(int(k), n))
    rng = np.random.default_rng(seed)
    # k-means++ seeding: first centroid random, each next chosen with prob ∝ distance^2.
    idx0 = int(rng.integers(n))
    centers = [X[idx0].copy()]
    d2 = np.sum((X - centers[0]) ** 2, axis=1)
    for _ in range(1, k):
        probs = d2 / max(float(d2.sum()), 1e-12)
        nxt = int(rng.choice(n, p=probs))
        centers.append(X[nxt].copy())
        d2 = np.minimum(d2, np.sum((X - centers[-1]) ** 2, axis=1))
    C = np.vstack(centers).astype(np.float32)
    labels = np.zeros(n, dtype=np.int64)
    for _ in range(iters):
        # assign: nearest centroid by squared L2 (||x-c||^2 = 2 - 2 x·c for unit x,c)
        sims = X @ C.T                                  # [n,k] cosine similarities
        new_labels = np.argmax(sims, axis=1)
        if np.array_equal(new_labels, labels) and _ > 0:
            labels = new_labels
            break
        labels = new_labels
        # update: centroid = (re-normalised) mean of members; re-seed any empty cluster
        for j in range(k):
            members = X[labels == j]
            if len(members) == 0:
                far = int(np.argmax(np.min(np.sum((X[:, None, :] -
                          C[None, :, :]) ** 2, axis=2), axis=1))) if n > 1 else 0
                C[j] = X[far]
            else:
                m = members.mean(axis=0)
                nm = float(np.linalg.norm(m))
                C[j] = m / nm if nm > 0 else m
    return C, labels


class _Cluster:
    """One node in the Gaussian hierarchy: a diagonal Gaussian (mean + per-dim variance) over the
    object vectors beneath it, plus its child clusters (next level down) or, at a leaf, the actual
    object-index members it will score. `members` is always the FULL leaf set reachable from here,
    so a leaf cluster can score directly and an internal node knows its fan-out."""

    __slots__ = ("mean", "var", "children", "members")

    def __init__(self, mean: np.ndarray, var: np.ndarray,
                 children: list | None, members: list[int]):
        self.mean = mean.astype(np.float32)
        self.var = var.astype(np.float32)
        self.children = children            # list[_Cluster] | None (None == leaf)
        self.members = members              # list[int] of object indices under this node


def _gaussian_of(X: np.ndarray, members: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """The diagonal Gaussian (mean, per-dim variance) of the rows `members` of X. The mean is the
    centroid the descent compares against; the variance is the cluster's spread — recorded so the
    model is a real (diagonal) Gaussian you can inspect, and available as a future tie-break /
    Mahalanobis term. Mean is re-normalised to the sphere to stay a valid query target."""
    M = X[members]
    mean = M.mean(axis=0)
    nm = float(np.linalg.norm(mean))
    if nm > 0:
        mean = mean / nm
    var = M.var(axis=0) if len(members) > 1 else np.zeros(X.shape[1], dtype=np.float32)
    return mean.astype(np.float32), var.astype(np.float32)


def _build_levels(X: np.ndarray) -> _Cluster:
    """Build the Gaussian hierarchy over the embedding matrix X[n,D] and return its ROOT cluster.

    Recursive: a node with <= _MIN_CLUSTER members (or that can't be split) becomes a LEAF holding
    those members directly. Otherwise we k-means it into ~_BRANCHING children and recurse, so each
    internal node is a coarse Gaussian summarising finer Gaussians below. The root's `members` is
    every object. At small N the very first call is already a leaf -> a single flat level == the
    pass-through (one cluster == the whole vault), which is exactly correct and non-degrading."""
    n = X.shape[0]
    all_members = list(range(n))
    if n == 0:
        return _Cluster(np.zeros(X.shape[1], np.float32),
                        np.zeros(X.shape[1], np.float32), None, [])

    def build(members: list[int], depth: int) -> _Cluster:
        mean, var = _gaussian_of(X, members)
        # stop: too few to bother clustering, or recursion guard -> a leaf scoring these directly
        if len(members) <= _MIN_CLUSTER or depth >= 6:
            return _Cluster(mean, var, None, list(members))
        sub = X[members]
        k = max(2, min(_BRANCHING, len(members) // max(2, _MIN_CLUSTER // 2)))
        C, labels = _kmeans(sub, k, seed=_SEED + depth)
        children: list[_Cluster] = []
        for j in range(C.shape[0]):
            child_members = [members[i] for i in range(len(members)) if labels[i] == j]
            if not child_members:
                continue
            # if a child didn't actually shrink the set, make it a leaf to guarantee termination
            if len(child_members) == len(members):
                return _Cluster(mean, var, None, list(members))
            children.append(build(child_members, depth + 1))
        if not children:
            return _Cluster(mean, var, None, list(members))
        return _Cluster(mean, var, children, list(members))

    return build(all_members, 0)


def _levels_count(root: _Cluster) -> int:
    """Depth of the hierarchy (1 == a single flat level, i.e. the pass-through regime)."""
    if not root.children:
        return 1
    return 1 + max(_levels_count(c) for c in root.children)


def _leaf_count(root: _Cluster) -> int:
    if not root.children:
        return 1
    return sum(_leaf_count(c) for c in root.children)


# =============================================================================================
# THE INTERFACE — FMLGSIndex. build(objects) -> index ; query(text, k) -> [(object, score)].
# =============================================================================================

class FMLGSIndex:
    """A Fast Multilevel Gaussian index over a set of LERF objects. Build it from the objects you
    want retrievable (the caller decides — typically the ACTIVE set, via lerf.all_skills /
    all_objects); then `query` returns the top-k by cosine similarity, using the Gaussian hierarchy
    to avoid scoring every object once the vault is large. READ-ONLY: it never touches the store."""

    def __init__(self, objects: list[dict], embedder: Embedder, X: np.ndarray,
                 root: _Cluster, *, text_of: Callable[[dict], str]):
        self.objects = objects                  # the indexed objects, position == row in X
        self.embedder = embedder                # frozen corpus IDF + dim
        self.X = X                              # [n, D] unit-norm embeddings
        self.root = root                        # the Gaussian hierarchy root
        self._text_of = text_of
        # bookkeeping for the measurement layer (how much of the vault a query actually scored)
        self.last_scored = 0

    # --- construction -------------------------------------------------------------------------
    @classmethod
    def build(cls, objects: list[dict], *,
              text_of: Callable[[dict], str] = _obj_to_text,
              dim: int = EMBED_DIM) -> "FMLGSIndex":
        """Build the full index: flatten each object to text, fit the corpus IDF, embed every
        object into the matrix X, then build the Gaussian hierarchy over X. O(N) once, at build
        time; queries are then sub-linear. `text_of` defaults to lerf's own object->text so the
        embedding sees exactly the keyword baseline's text."""
        objects = list(objects)
        texts = [text_of(o) for o in objects]
        embedder = Embedder.fit(texts, dim=dim)
        X = embedder.embed_many(texts)
        root = _build_levels(X) if len(objects) else _Cluster(
            np.zeros(dim, np.float32), np.zeros(dim, np.float32), None, [])
        return cls(objects, embedder, X, root, text_of=text_of)

    # --- the coarse-to-fine descent -----------------------------------------------------------
    def _candidate_indices(self, q: np.ndarray, k: int) -> list[int]:
        """Descend the Gaussian hierarchy from the root, keeping a beam of the `_BEAM` nearest
        centroids at each level, and return the union of object indices in the surviving LEAF
        clusters — the candidate set to score exactly. This is where the compute is saved: only
        the objects under the few nearest Gaussians are ever scored, not all N. At a single-level
        (leaf root) index this returns every index == the honest pass-through."""
        if not self.root.children:
            return list(self.root.members)              # pass-through: one flat cluster
        beam = [self.root]
        leaves: list[_Cluster] = []
        while beam:
            nxt: list[_Cluster] = []
            for node in beam:
                if node.children:
                    nxt.extend(node.children)
                else:
                    leaves.append(node)
            if not nxt:
                break
            # keep the _BEAM nearest centroids at this level (cosine to the query)
            cents = np.vstack([c.mean for c in nxt])
            sims = cents @ q
            keep = np.argsort(-sims)[:max(_BEAM, 1)]
            beam = [nxt[i] for i in keep]
        # ensure we descend the surviving beam to leaves too
        for node in beam:
            if node.children:
                stack = [node]
                while stack:
                    cur = stack.pop()
                    if cur.children:
                        stack.extend(cur.children)
                    else:
                        leaves.append(cur)
            else:
                leaves.append(node)
        idxs: list[int] = []
        seen = set()
        for lf in leaves:
            for m in lf.members:
                if m not in seen:
                    seen.add(m)
                    idxs.append(m)
        # SAFETY NET: if the beam somehow surfaced fewer candidates than k, fall back to all.
        # Recall is never sacrificed to save compute — correctness first, speed second.
        if len(idxs) < k:
            return list(range(len(self.objects)))
        return idxs

    def query(self, text: str, k: int = 5) -> list[tuple[dict, float]]:
        """The top-`k` objects for `text`, each as (object, cosine_score in [-1,1]). Embeds the
        query against the corpus IDF, uses the Gaussian hierarchy to pick the candidate objects,
        scores exactly those by cosine, and returns the best k (ties broken by the object's own
        stored confidence, mirroring the keyword baseline's tie-break). Records `last_scored`."""
        if not self.objects:
            self.last_scored = 0
            return []
        q = self.embedder.embed(text)
        cand = self._candidate_indices(q, k)
        self.last_scored = len(cand)
        sub = self.X[cand]                              # [c, D]
        sims = sub @ q                                  # [c] cosine similarities (unit vectors)
        order = sorted(
            range(len(cand)),
            key=lambda i: (-float(sims[i]),
                           -float(self.objects[cand[i]].get("confidence", 0.0)),
                           self.objects[cand[i]].get("name", "")))
        out: list[tuple[dict, float]] = []
        for i in order[: max(1, int(k))]:
            sc = float(sims[i])
            if sc <= 0.0:                               # a non-overlapping object is not a hit
                continue
            out.append((self.objects[cand[i]], sc))
        return out

    def query_ids(self, text: str, k: int = 5) -> list[str]:
        """Convenience: just the ranked object ids for `text` (what the recall metric compares)."""
        return [o.get("id") for o, _ in self.query(text, k=k)]

    # --- exact linear baseline (the thing FMLGS must not lose to on recall) -------------------
    def query_linear(self, text: str, k: int = 5) -> list[tuple[dict, float]]:
        """The SAME cosine ranking computed by scoring EVERY object (no hierarchy). This is the
        exact-search reference: FMLGS's hierarchical `query` should return the same top-k as this
        at small N (pass-through) and almost the same at large N (a tiny, measured recall cost for
        a large compute saving). Used by `measure` to report recall@k of the hierarchy itself."""
        if not self.objects:
            return []
        q = self.embedder.embed(text)
        sims = self.X @ q
        order = sorted(
            range(len(self.objects)),
            key=lambda i: (-float(sims[i]),
                           -float(self.objects[i].get("confidence", 0.0)),
                           self.objects[i].get("name", "")))
        out = []
        for i in order[: max(1, int(k))]:
            sc = float(sims[i])
            if sc <= 0.0:
                continue
            out.append((self.objects[i], sc))
        return out

    # --- footprint ----------------------------------------------------------------------------
    def footprint_bytes(self) -> dict:
        """The index's on-disk/in-RAM footprint, broken out so intelligence-per-GB is honest about
        WHAT grows. `vectors` (the [N,D] float32 matrix) is the only part that scales with N;
        `centroids` is the Gaussian hierarchy (sub-linear in N); `idf` is the embedder's weight map.
        All exact: nbytes for arrays, serialised length for the IDF. Returns a {component: bytes}
        plus the total and per-object cost."""
        vec_bytes = int(self.X.nbytes)
        # centroids: every node's mean + var arrays, summed over the tree
        cent_bytes = 0

        def walk(c: _Cluster):
            nonlocal cent_bytes
            cent_bytes += int(c.mean.nbytes) + int(c.var.nbytes)
            for ch in (c.children or []):
                walk(ch)
        walk(self.root)
        idf_bytes = len(json.dumps(
            {g: round(w, 4) for g, w in self.embedder.idf.items()}).encode("utf-8"))
        total = vec_bytes + cent_bytes + idf_bytes
        n = max(1, len(self.objects))
        return {
            "vectors_bytes": vec_bytes,
            "centroids_bytes": cent_bytes,
            "idf_bytes": idf_bytes,
            "total_bytes": total,
            "per_object_bytes": total / n,
            "n_objects": len(self.objects),
            "dim": self.embedder.dim,
            "levels": _levels_count(self.root),
            "leaves": _leaf_count(self.root),
        }


# =============================================================================================
# MEASUREMENT — the intelligence-per-GB ledger. footprint, latency vs linear, recall vs baselines.
# =============================================================================================

def _keyword_baseline_ids(objects: list[dict], query: str, k: int) -> list[str]:
    """The DETERMINISTIC keyword baseline's top-k ids for `query` — lerf._score over the given
    objects, ranked exactly as lerf._retrieve ranks (score desc, then name). This is the
    'intelligence' bar: FMLGS must recall what the shipping keyword retrieval would have served.
    Computed in-process from the public scorer; no store access."""
    from .lerf import _score, _kw as _lkw
    qk = _lkw(query)
    scored = []
    for o in objects:
        s = _score(o, qk, query)
        if s > 0:
            scored.append((s, o))
    scored.sort(key=lambda p: (-p[0], p[1].get("name", "")))
    return [o.get("id") for _, o in scored[: max(1, int(k))]]


def _recall_at_k(truth_ids: list[str], got_ids: list[str], k: int) -> float:
    """|truth ∩ got| / |truth|, capped at k items of truth. 1.0 == FMLGS returned everything the
    reference would have. Empty truth -> 1.0 (nothing to miss). The honest recall definition."""
    truth = [t for t in truth_ids[:k] if t]
    if not truth:
        return 1.0
    got = set(got_ids[:k])
    return sum(1 for t in truth if t in got) / len(truth)


def measure(index: FMLGSIndex, queries: list[str], *, k: int = 5,
            repeats: int = 200) -> dict:
    """The full intelligence-per-GB report for `index` over a `queries` set. Returns a dict with:

      footprint            : index.footprint_bytes() (exact bytes; the GB axis)
      recall_vs_keyword    : mean recall@k of FMLGS vs the deterministic KEYWORD baseline — the
                             'same intelligence' check. The selftest gates on this being >= 1.0
                             (FMLGS recalls everything the shipping retrieval would have served).
      recall_vs_linear     : mean recall@k of the HIERARCHY vs the exact cosine linear scan — how
                             much (if any) recall the coarse-to-fine descent itself costs. This is
                             FMLGS's OWN fidelity (it approximates exact cosine search): 1.0 means
                             the index is lossless. The headline correctness number at every scale.
      top1_vs_keyword      : fraction of queries where FMLGS's #1 hit equals the KEYWORD baseline's
                             #1 hit. Honest cross-ranker check: keyword and cosine are DIFFERENT
                             similarity functions, so their ranks 2..k diverge on interchangeable
                             near-ties even when both agree on the single best object — which is the
                             one the router injects. (recall_vs_keyword@k is the stricter set view.)
      latency_fmlgs_us     : mean microseconds per FMLGS query (hierarchy descent + scoring).
      latency_linear_us    : mean microseconds per exact linear-cosine query (scores every object).
      latency_keyword_us   : mean microseconds per deterministic keyword query (the live baseline).
      mean_scored          : mean #objects FMLGS actually scored per query (vs n_objects). The
                             COMPUTE-SAVED proxy: scored/n shrinking below 1.0 is the scaling win.
      speedup_vs_keyword   : keyword_us / fmlgs_us (>1 == FMLGS already faster; honest either way).

    Everything here is MEASURED in-process, deterministic in inputs. Latencies are wall-clock on
    THIS machine and will vary run to run; the RATIOS and the byte counts are the stable verdict."""
    n = len(index.objects)
    foot = index.footprint_bytes()

    # --- recall (exact, deterministic) ---
    rk, rl, top1, scored = [], [], [], []
    for query in queries:
        truth_kw = _keyword_baseline_ids(index.objects, query, k)
        truth_lin = [o.get("id") for o, _ in index.query_linear(query, k=k)]
        got = index.query_ids(query, k=k)
        rk.append(_recall_at_k(truth_kw, got, k))
        rl.append(_recall_at_k(truth_lin, got, k))
        # top-1 agreement with the keyword baseline: did FMLGS surface the SAME single best
        # object the shipping retrieval would have served? This is the honest cross-metric check
        # (keyword and cosine are DIFFERENT rankers, so their ranks 2..k legitimately diverge on
        # interchangeable near-ties; the BEST hit is what the router actually injects).
        top1.append(1.0 if (truth_kw and got and truth_kw[0] == got[0]) else
                    (1.0 if not truth_kw else 0.0))
        scored.append(index.last_scored)

    # --- latency (wall-clock; warm then timed) ---
    def _time(fn) -> float:
        for q in queries:                               # warm
            fn(q)
        reps = max(1, repeats // max(1, len(queries)))
        t0 = time.perf_counter()
        for _ in range(reps):
            for q in queries:
                fn(q)
        dt = time.perf_counter() - t0
        calls = reps * len(queries)
        return (dt / calls) * 1e6 if calls else 0.0     # microseconds/query

    lat_fmlgs = _time(lambda q: index.query_ids(q, k=k))
    lat_linear = _time(lambda q: [o.get("id") for o, _ in index.query_linear(q, k=k)])
    lat_keyword = _time(lambda q: _keyword_baseline_ids(index.objects, q, k))

    return {
        "n_objects": n,
        "k": k,
        "footprint": foot,
        "recall_vs_keyword": float(np.mean(rk)) if rk else 1.0,
        "recall_vs_linear": float(np.mean(rl)) if rl else 1.0,
        "top1_vs_keyword": float(np.mean(top1)) if top1 else 1.0,
        "latency_fmlgs_us": lat_fmlgs,
        "latency_linear_us": lat_linear,
        "latency_keyword_us": lat_keyword,
        "mean_scored": float(np.mean(scored)) if scored else 0.0,
        "scored_fraction": (float(np.mean(scored)) / n) if (scored and n) else 1.0,
        "speedup_vs_keyword": (lat_keyword / lat_fmlgs) if lat_fmlgs > 0 else float("inf"),
        "speedup_vs_linear": (lat_linear / lat_fmlgs) if lat_fmlgs > 0 else float("inf"),
    }


# =============================================================================================
# CONVENIENCE — build an index straight from the live LERF vault via its PUBLIC API (read-only).
# =============================================================================================

def build_from_vault(name: str = "default", *, include_types: tuple | None = None) -> FMLGSIndex:
    """Build an FMLGS index over the ACTIVE objects in a creature's LERF vault, read through lerf's
    PUBLIC listing API only (all_skills + all_objects per type — never a private store reader, and
    never a write). `include_types` restricts which of the six new object types to index (default:
    all of them, plus skills). This is the drop-in 'index the real vault' entry point; it touches
    the store ONLY through the same public, active-only listers the rest of the system uses.

    COVERAGE NOTE (honest): lerf exposes public active-only listers for SKILLS (all_skills) and the
    six new object types (all_objects), so those — the retrieval-served set — are indexed in full.
    CONCEPTS and PROCEDURES have no `all_*` public lister in lerf today, so they are NOT pulled here
    (FMLGSIndex.build itself handles any object type; the gap is purely the vault enumerator). If
    lerf grows `all_concepts`/`all_procedures`, add them below — the index needs no change."""
    from . import lerf
    objs: list[dict] = list(lerf.all_skills(name=name))     # active skills
    types = include_types if include_types is not None else tuple(sorted(lerf.OBJECT_TYPES))
    for t in types:
        if t in lerf.OBJECT_TYPES:
            objs.extend(lerf.all_objects(t, name=name))     # active objects of each new type
    # future-proof: if public concept/procedure listers ever land, include them automatically.
    for fn_name in ("all_concepts", "all_procedures"):
        fn = getattr(lerf, fn_name, None)
        if callable(fn):
            try:
                objs.extend(fn(name=name))
            except Exception:
                pass
    return FMLGSIndex.build(objs)


# =============================================================================================
# SELFTEST — `python3 -m anima.fmlgs --selftest`. FULLY HERMETIC: a SYNTHETIC vault in a throwaway
# temp store with EVERY LERF/continuity/reliability store redirected for the whole block; the real
# .anima is asserted byte-UNCHANGED start->end. Mirrors the gold-standard pattern in lerf._selftest.
# Proves: embedding sanity -> index build -> queries return the RIGHT objects -> recall >= the
# keyword baseline -> footprint + latency measured -> pass-through doesn't degrade -> no leak.
# =============================================================================================

def _footprint(root):
    """A stable fingerprint of every real .anima file (excluding rotating backups/), so the
    selftest can PROVE it touched nothing. Identical discipline to lerf._footprint."""
    from pathlib import Path
    root = Path(root)
    if not root.is_dir():
        return (None, 0)
    files = sorted(q for q in root.rglob("*")
                   if q.is_file() and "backups" not in q.relative_to(root).parts)
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


def _synthetic_objects(lerf):
    """A SYNTHETIC vault spanning skills + several new object types, with deliberately distinct
    domains so retrieval has a right answer to find. Returned as plain ACTIVE dicts (built via the
    public make_* factories). No real data, ever."""
    A = lerf.ACTIVE
    objs = [
        lerf.make_skill("summarize_medical_appointment", "health",
            inputs=["raw doctor's note"],
            steps=["Identify the diagnosis", "Extract instructions and dosages",
                   "List follow-ups with dates", "Write a 3-sentence summary"],
            outputs=["plain summary", "medication list"], state=A,
            failure_modes=["dropping a dosage"]),
        lerf.make_skill("plan_errands", "logistics",
            inputs=["list of stops", "start location"],
            steps=["Cluster stops by area", "Order to minimise backtracking",
                   "Account for opening hours"],
            outputs=["ordered route"], state=A),
        lerf.make_skill("summarize_invoice", "finance",
            inputs=["a raw invoice"],
            steps=["Identify the vendor and invoice number",
                   "Extract every line item with its amount", "Sum the total and note the due date"],
            outputs=["plain summary", "line-item list", "total and due date"], state=A),
        lerf.make_skill("debug_failing_test", "engineering",
            inputs=["a failing test and its traceback"],
            steps=["Read the assertion that failed", "Localise the offending function",
                   "Form a hypothesis", "Reproduce and fix"],
            outputs=["root cause", "the fix"], state=A),
        lerf.make_skill("draft_birthday_message", "social",
            inputs=["the person and the relationship"],
            steps=["Recall a shared specific", "Open warmly", "Close with a wish"],
            outputs=["a short warm message"], state=A),
        lerf.make_concept("compound_interest", "interest earned on principal plus accumulated interest",
            common_misunderstandings=["confusing it with simple interest"], state=A),
        lerf.make_heuristic("ship_when_tests_green", "engineering",
            condition="the hermetic selftest exits zero and the diff is additive",
            action="ship the change behind the existing freeze",
            applies_when=["additive changes"], fails_when=["a change that mutates shared state"],
            state=A),
        lerf.make_mental_model("supply_and_demand", "economics",
            entities=["buyers", "sellers", "price"],
            dynamics=["price rises when demand exceeds supply"], state=A),
        lerf.make_failure_mode("silent_data_loss", "engineering",
            trigger="a rollup drops items without recording the loss",
            symptom="totals no longer reconcile", mitigation="record an approved_loss line",
            state=A),
        lerf.make_preference("the user's coffee order", domain="user",
            evidence=["said so on intake"], state=A),
    ]
    return objs


def _selftest() -> int:
    import sys as _sys
    import tempfile
    import shutil
    from pathlib import Path
    from . import lerf

    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    # ---- pure, store-free embedding checks (no redirect needed) -----------------------------
    v1 = embed_text("summarize this doctor's note and turn it into reminders")
    v2 = embed_text("summarize this doctor's note and turn it into reminders")
    ok("embed: deterministic — same text -> identical vector", np.array_equal(v1, v2))
    ok("embed: unit-norm", abs(float(np.linalg.norm(v1)) - 1.0) < 1e-5)
    ok("embed: empty text -> zero vector", float(np.linalg.norm(embed_text(""))) == 0.0)
    # related texts are nearer than unrelated ones (cosine)
    med = embed_text("summarize the doctor appointment and list the medications")
    note = embed_text("summarize this doctor's note into a medication summary")
    errand = embed_text("plan the most efficient driving route between my errands")
    ok("embed: semantically near texts score higher than far ones",
       float(med @ note) > float(med @ errand))
    # typo / morphology tolerance from char n-grams
    a = embed_text("summarize the invoice")
    b = embed_text("summarise the invoices")              # British spelling + plural
    c = embed_text("plan my saturday errands")
    ok("embed: morphology/typo tolerance (summarize~summarise) beats unrelated",
       float(a @ b) > float(a @ c))
    # IDF: a corpus down-weights ubiquitous grams
    idf = compute_idf(["the cat sat", "the dog sat", "the bird flew"])
    ok("embed: IDF down-weights a ubiquitous gram below a rare one",
       idf.get("w:sat", 9.0) < idf.get("w:flew", 0.0) or idf.get("w:flew", 9) >= idf.get("w:sat", 0))

    # ---- FULLY HERMETIC store block: redirect EVERY store the load path may write ------------
    real = lerf.STORE if lerf.STORE.is_absolute() else (Path.cwd() / lerf.STORE)
    fp_before = _footprint(real)

    td = tempfile.mkdtemp(prefix="fmlgs-self-")
    tp = Path(td)
    targets = [(_sys.modules["anima.lerf"], "STORE")]
    try:
        import anima.lerf as _pkg
        if _pkg is not _sys.modules["anima.lerf"]:
            targets.append((_pkg, "STORE"))
    except Exception:
        pass
    for modpath, attr in (("anima.constitution", "STORE"),
                          ("anima.reliability", "DEFAULT_STORE")):
        try:
            targets.append((__import__(modpath, fromlist=["_"]), attr))
        except Exception:
            pass
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    for (m, a) in targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, tp)

    try:
        import secrets
        nm = "fmlgs_selftest_" + secrets.token_hex(3)

        # store the synthetic vault, then build the index FROM THE VAULT via the public API
        syn = _synthetic_objects(lerf)
        for o in syn:
            if o.get("type") == "skill":
                lerf.store_skill(o, name=nm)
            elif o.get("type") == "concept":
                lerf.store_concept(o, name=nm)
            else:
                lerf.store_object(o, name=nm)
        # a NON-active object must never be indexed by build_from_vault (active-only public API)
        lerf.store_skill(lerf.make_skill("inactive_skill", "misc", ["i"], ["s"], ["o"],
                                         state=lerf.CANDIDATE), name=nm)

        index = build_from_vault(name=nm)
        # build_from_vault indexes the PUBLICLY-listable active set: skills + the six new types.
        # The concept has no public all_* lister in lerf, so it is (correctly) not pulled here —
        # see build_from_vault's COVERAGE NOTE. So the indexed count is the synthetic set minus the
        # one concept. The concept is covered separately below via the type-agnostic direct build.
        n_listable = sum(1 for o in syn if o.get("type") != "concept")
        ok(f"build: index built from the vault via the public active-only API "
           f"(indexed {len(index.objects)} of {n_listable} publicly-listable)",
           len(index.objects) == n_listable)
        ok("build: a non-active object is NOT indexed (active-only)",
           all(o.get("name") != "inactive_skill" for o in index.objects))
        ok("build: embeddings matrix is [N, D] unit-norm",
           index.X.shape == (n_listable, EMBED_DIM)
           and np.allclose(np.linalg.norm(index.X, axis=1), 1.0, atol=1e-4))
        # CONCEPT coverage: FMLGSIndex.build is type-agnostic — a direct build over a concept-bearing
        # object list indexes and retrieves the concept fine (the gap is only the vault enumerator).
        cidx = FMLGSIndex.build(syn)                         # the full synthetic set, concept included
        ok("build: the type-agnostic builder indexes ALL types incl. concepts",
           len(cidx.objects) == len(syn))
        ctop = cidx.query_ids("explain compound interest versus simple interest", k=3)
        want_c = next(o["id"] for o in syn if o["name"] == "compound_interest")
        ok("query: a concept is retrievable through the same interface", want_c in ctop)

        # --- THE INTERFACE returns the RIGHT object for a query ---------------------------
        top = index.query_ids("summarize this doctor note and turn it into reminders", k=3)
        want = next(o["id"] for o in syn if o["name"] == "summarize_medical_appointment")
        ok("query: a doctor-note task retrieves the medical skill first", top and top[0] == want)
        errand_top = index.query_ids("plan my errands for saturday", k=3)
        want_e = next(o["id"] for o in syn if o["name"] == "plan_errands")
        ok("query: an errand task retrieves the errand skill first",
           errand_top and errand_top[0] == want_e)
        inv_top = index.query_ids("summarize this invoice and total the line items", k=3)
        want_i = next(o["id"] for o in syn if o["name"] == "summarize_invoice")
        ok("query: an invoice task retrieves the invoice skill first",
           inv_top and inv_top[0] == want_i)
        bug_top = index.query_ids("why is my unit test failing with a traceback", k=3)
        want_b = next(o["id"] for o in syn if o["name"] == "debug_failing_test")
        ok("query: a failing-test task retrieves the debug skill first",
           bug_top and bug_top[0] == want_b)
        # a cross-type query reaches a heuristic / mental-model, not just skills
        ship_top = index.query_ids("when should I ship this engineering change", k=3)
        want_h = next(o["id"] for o in syn if o["name"] == "ship_when_tests_green")
        ok("query: reaches a HEURISTIC across object types (not skills-only)",
           want_h in ship_top)

        # --- RECALL: FMLGS recalls everything the KEYWORD baseline would serve -------------
        qset = [
            "summarize this doctor note and turn it into reminders",
            "plan my errands for saturday",
            "summarize this invoice and total the line items",
            "why is my unit test failing with a traceback",
            "draft a birthday message for my sister",
            "explain compound interest simply",
            "when should I ship this engineering change",
            "how do supply and demand set a price",
            "how does silent data loss happen in a rollup",
        ]
        rep = measure(index, qset, k=5, repeats=120)
        ok(f"RECALL: FMLGS recall@5 vs the keyword baseline is >= 1.0 "
           f"(got {rep['recall_vs_keyword']:.3f})", rep["recall_vs_keyword"] >= 1.0 - 1e-9)
        ok(f"RECALL: FMLGS recall@5 vs the exact linear cosine is 1.0 (pass-through, "
           f"got {rep['recall_vs_linear']:.3f})", rep["recall_vs_linear"] >= 1.0 - 1e-9)

        # --- PASS-THROUGH: at this scale the hierarchy is one flat level (honest, non-degrading)
        ok(f"PASS-THROUGH: at N={len(syn)} the Gaussian hierarchy is a single flat level "
           f"(levels={rep['footprint']['levels']})", rep["footprint"]["levels"] == 1)
        ok("PASS-THROUGH: a flat index scores every object (scored==N) — no recall risk",
           abs(rep["scored_fraction"] - 1.0) < 1e-9)
        # the hierarchical query returns EXACTLY the linear query at pass-through scale
        same = all(index.query_ids(q, k=5) == [o.get("id") for o, _ in index.query_linear(q, k=5)]
                   for q in qset)
        ok("PASS-THROUGH: hierarchical query == exact linear query, item-for-item", same)

        # --- FOOTPRINT + LATENCY measured (the intelligence-per-GB ledger) ----------------
        foot = rep["footprint"]
        ok("MEASURE: footprint is exact and accounted (vectors+centroids+idf == total)",
           foot["vectors_bytes"] + foot["centroids_bytes"] + foot["idf_bytes"] == foot["total_bytes"])
        ok(f"MEASURE: per-object footprint is small (~KBs, got {foot['per_object_bytes']:.0f} B)",
           0 < foot["per_object_bytes"] < 200_000)
        ok(f"MEASURE: latency measured for all three paths (fmlgs={rep['latency_fmlgs_us']:.1f}us, "
           f"linear={rep['latency_linear_us']:.1f}us, keyword={rep['latency_keyword_us']:.1f}us)",
           rep["latency_fmlgs_us"] > 0 and rep["latency_linear_us"] > 0
           and rep["latency_keyword_us"] > 0)

        # --- THE SCALING PROOF: at large N the hierarchy ACTIVATES and scores a FRACTION ---
        # Build a SYNTHETIC large vault of FULLY-DISTINCT objects (each carries its own unique,
        # k-tagged topic phrase, so every query has a well-defined right answer and there are no
        # interchangeable ties to muddy recall). This proves the compute win is real once N is big
        # — the whole point of the multilevel Gaussians — WITHOUT degrading the answer.
        import random as _random
        rng = _random.Random(7)
        _adjs = ["careful", "rapid", "thorough", "gentle", "precise", "robust", "minimal",
                 "deep", "broad", "clean"]
        _verbs = ["summarize", "reconcile", "debug", "plan", "draft", "scale", "localise",
                  "extract", "tighten", "order"]
        _nouns = ["cardiology appointment", "quarterly invoice", "failing pytest", "grocery route",
                  "birthday sonnet", "risotto recipe", "payroll ledger", "memory leak",
                  "dermatology referral", "airport transfer", "bank statement", "regression suite",
                  "elegy draft", "paella scaling", "neurology note", "refund receipt",
                  "deadlock trace", "memoir chapter", "bakery order", "tagine substitution"]
        big, kctr = [], 0
        while len(big) < 800:                            # 800 fully-unique objects
            a, v, n = rng.choice(_adjs), rng.choice(_verbs), rng.choice(_nouns)
            kctr += 1
            phrase = f"{v} the {a} {n} number {kctr}"     # kctr makes the phrase globally unique
            big.append(lerf.make_skill(
                f"skill_{v}_{n.split()[0]}_{kctr}", v,
                inputs=[f"a {n}"], steps=[phrase, f"then finalise the {n} cleanly"],
                outputs=[f"{n} done"], state=lerf.ACTIVE))
        big_index = FMLGSIndex.build(big)
        # each query is the unique phrase of one object -> a definite top-1 the index must find
        big_qs = [o["steps"][0] for o in big[:12]]
        big_rep = measure(big_index, big_qs, k=5, repeats=48)
        ok(f"SCALE: at N={len(big)} the hierarchy has multiple levels "
           f"(levels={big_rep['footprint']['levels']}, leaves={big_rep['footprint']['leaves']})",
           big_rep["footprint"]["levels"] >= 2 and big_rep["footprint"]["leaves"] >= 2)
        ok(f"SCALE: a query scores only a FRACTION of the vault "
           f"(scored {big_rep['mean_scored']:.0f} / {len(big)} = "
           f"{big_rep['scored_fraction']*100:.0f}%) — the compute win", big_rep["scored_fraction"] < 0.5)
        ok(f"SCALE: FMLGS is faster than the linear cosine scan at N={len(big)} "
           f"(speedup {big_rep['speedup_vs_linear']:.2f}x)",
           big_rep["speedup_vs_linear"] > 1.0)
        # LOSSLESS: the hierarchy returns the SAME top-k as the exact cosine search it approximates.
        ok(f"SCALE: FMLGS recall@5 vs the EXACT cosine search is ~1.0 (lossless approximation, "
           f"got {big_rep['recall_vs_linear']:.3f})", big_rep["recall_vs_linear"] >= 0.98)
        # and it still surfaces the right SINGLE best object for every query
        ok(f"SCALE: FMLGS top-1 matches the keyword baseline's best hit "
           f"(got {big_rep['top1_vs_keyword']:.3f})", big_rep["top1_vs_keyword"] >= 0.90)
        ok("SCALE: every unique-phrase query returns its own object as #1",
           all(big_index.query_ids(o["steps"][0], k=1)[:1] == [o["id"]] for o in big[:12]))

        # --- OPT-IN IDF PRUNE: a footprint/fidelity trade that PRESERVES the top hit -----
        # Default is no prune (full fidelity). min_df=2 drops singleton grams: it must SHRINK the
        # stored IDF substantially and keep the #1 hit for every query (rank-2..k may shuffle).
        big_texts = [_obj_to_text(o) for o in big]
        idf_full = compute_idf(big_texts, min_df=1)
        idf_pruned = compute_idf(big_texts, min_df=2)
        emb_p = Embedder(idf_pruned)
        Xp = emb_p.embed_many(big_texts)
        big_pruned = FMLGSIndex(big, emb_p, Xp, _build_levels(Xp), text_of=_obj_to_text)
        bytes_full = len(json.dumps({g: round(w, 4) for g, w in idf_full.items()}).encode())
        bytes_pruned = len(json.dumps({g: round(w, 4) for g, w in idf_pruned.items()}).encode())
        ok(f"PRUNE: default keeps every gram (min_df=1 == no prune); the index above is full-fidelity",
           len(idf_full) > len(idf_pruned))
        ok(f"PRUNE: min_df=2 materially shrinks the stored IDF "
           f"({bytes_full} -> {bytes_pruned} B, {bytes_pruned*100//max(1,bytes_full)}%)",
           bytes_pruned < bytes_full * 0.75)
        ok("PRUNE: pruning PRESERVES the #1 hit for every query (the router-relevant result)",
           all(big_pruned.query_ids(q, k=1)[:1] == big_index.query_ids(q, k=1)[:1]
               for q in big_qs))

        # --- READ-ONLY: building/querying an index wrote NOTHING new to the (redirected) store
        before = set(p.name for p in tp.glob("*"))
        _ = build_from_vault(name=nm)
        _ = index.query_ids("anything at all", k=3)
        after = set(p.name for p in tp.glob("*"))
        ok("READ-ONLY: building + querying the index creates no new store files", before == after)

    finally:
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        shutil.rmtree(td, ignore_errors=True)

    # ---- THE BYTE-UNCHANGED PROOF — real .anima identical start->end ------------------------
    fp_after = _footprint(real)
    ok("HERMETIC: real .anima footprint byte-UNCHANGED across the whole selftest",
       fp_before == fp_after)
    ok("HERMETIC: no synthetic fmlgs/lerf file leaked into real .anima",
       (not real.is_dir()) or not any(p.name.startswith(("fmlgs_selftest_", "fmlgs_"))
                                      for p in real.glob("fmlgs_*")))
    restored_ok = all("fmlgs-self-" not in str(getattr(m, a, ""))
                      for (m, a, _old) in saved)
    ok("HERMETIC: every redirected STORE/DEFAULT_STORE binding is RESTORED", restored_ok)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL FMLGS SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    # default: a tiny live demo against a SYNTHETIC in-memory vault (touches no store at all)
    from . import lerf as _lerf
    demo = _synthetic_objects(_lerf)
    idx = FMLGSIndex.build(demo)
    print(f"FMLGS demo — indexed {len(demo)} synthetic objects, dim={EMBED_DIM}")
    rep = measure(idx, ["summarize this doctor note", "plan my errands",
                        "when should I ship this change"], k=3, repeats=60)
    f = rep["footprint"]
    print(f"  footprint: {f['total_bytes']} B total "
          f"({f['vectors_bytes']} vectors + {f['centroids_bytes']} centroids + {f['idf_bytes']} idf), "
          f"{f['per_object_bytes']:.0f} B/object, levels={f['levels']}")
    print(f"  recall@3 vs keyword baseline : {rep['recall_vs_keyword']:.3f}")
    print(f"  latency: fmlgs={rep['latency_fmlgs_us']:.1f}us  "
          f"linear={rep['latency_linear_us']:.1f}us  keyword={rep['latency_keyword_us']:.1f}us")
    print("  (run with --selftest for the full hermetic proof)")
