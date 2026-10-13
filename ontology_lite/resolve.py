"""Entity resolution: merge records from messy sources into canonical entities.

Pipeline: normalize -> block -> score pairs (with evidence) -> cluster (union-find).
Every merge decision carries an explanation so results are auditable.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Iterable


@dataclass(frozen=True)
class Record:
    source: str
    id: str
    fields: dict = field(default_factory=dict, hash=False, compare=False)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.id}"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def jaro(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    window = max(max(len(a), len(b)) // 2 - 1, 0)
    a_flags, b_flags = [False] * len(a), [False] * len(b)
    matches = 0
    for i, ch in enumerate(a):
        for j in range(max(0, i - window), min(len(b), i + window + 1)):
            if not b_flags[j] and b[j] == ch:
                a_flags[i] = b_flags[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    transpositions, k = 0, 0
    for i in range(len(a)):
        if a_flags[i]:
            while not b_flags[k]:
                k += 1
            if a[i] != b[k]:
                transpositions += 1
            k += 1
    t = transpositions / 2
    return (matches / len(a) + matches / len(b) + (matches - t) / matches) / 3


def similarity(a: str, b: str) -> float:
    """Jaro-Winkler similarity on normalized strings, in [0, 1]."""
    a, b = normalize(a), normalize(b)
    j = jaro(a, b)
    prefix = 0
    for x, y in zip(a[:4], b[:4]):
        if x != y:
            break
        prefix += 1
    return j + prefix * 0.1 * (1 - j)


def name_similarity(a: str, b: str) -> float:
    """Order-insensitive name comparison ('Smith, John' ~ 'John Smith', 'J. Smith' ~ 'John Smith')."""
    ta, tb = sorted(normalize(a).split()), sorted(normalize(b).split())
    if not ta or not tb:
        return 0.0
    full = similarity(" ".join(ta), " ".join(tb))
    # Token-wise best match, treating single-letter tokens as initials.
    scores = []
    for x in ta:
        best = 0.0
        for y in tb:
            if len(x) == 1 or len(y) == 1:
                best = max(best, 0.9 if x[0] == y[0] else 0.0)
            else:
                best = max(best, similarity(x, y))
        scores.append(best)
    token = sum(scores) / len(scores)
    return max(full, token)


def _digits(s: str) -> str:
    return re.sub(r"\D", "", str(s))


@dataclass
class Match:
    a: str
    b: str
    score: float
    evidence: dict


@dataclass
class Entity:
    id: str
    members: list[Record]
    matches: list[Match]

    def canonical(self, field_name: str):
        """Most common non-empty value for a field across members (ties -> longest)."""
        counts: dict[str, int] = defaultdict(int)
        for m in self.members:
            v = m.fields.get(field_name)
            if v:
                v = " ".join(str(v).split())
                if field_name == "name" and "," in v:  # "Smith, John" -> "John Smith"
                    last, _, first = v.partition(",")
                    v = f"{first.strip()} {last.strip()}"
                counts[v] += 1
        if not counts:
            return None
        return max(counts, key=lambda v: (counts[v], len(str(v))))


class _UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


class Resolver:
    """Resolve records into entities.

    Exact-identifier agreement (email, phone) is strong evidence; name similarity is
    weaker and requires corroboration. A conflicting strong identifier vetoes a merge.
    """

    def __init__(self, threshold: float = 0.85, name_field: str = "name",
                 email_field: str = "email", phone_field: str = "phone"):
        self.threshold = threshold
        self.name_field = name_field
        self.email_field = email_field
        self.phone_field = phone_field

    def _blocks(self, rec: Record) -> set[str]:
        keys = set()
        name = normalize(rec.fields.get(self.name_field, ""))
        for tok in name.split():
            if len(tok) > 1:
                keys.add("tok:" + tok[:3])
        email = str(rec.fields.get(self.email_field, "")).lower().strip()
        if email:
            keys.add("email:" + email)
        phone = _digits(rec.fields.get(self.phone_field, ""))
        if len(phone) >= 7:
            keys.add("phone:" + phone[-7:])
        return keys

    def score(self, a: Record, b: Record) -> Match | None:
        fa, fb = a.fields, b.fields
        evidence: dict = {}
        ea = str(fa.get(self.email_field, "")).lower().strip()
        eb = str(fb.get(self.email_field, "")).lower().strip()
        pa, pb = _digits(fa.get(self.phone_field, "")), _digits(fb.get(self.phone_field, ""))
        ns = name_similarity(fa.get(self.name_field, ""), fb.get(self.name_field, ""))
        evidence["name"] = round(ns, 3)

        email_eq = bool(ea) and ea == eb
        phone_eq = len(pa) >= 7 and len(pb) >= 7 and pa[-7:] == pb[-7:]
        email_conflict = bool(ea) and bool(eb) and ea != eb
        phone_conflict = len(pa) >= 7 and len(pb) >= 7 and pa[-7:] != pb[-7:]
        if email_eq:
            evidence["email"] = "exact"
        if phone_eq:
            evidence["phone"] = "exact"
        if email_conflict:
            evidence["email"] = "conflict"
        if phone_conflict:
            evidence["phone"] = "conflict"

        # Name alone tops out at 0.55, below any sane threshold: a merge needs
        # corroboration from a shared strong identifier.
        score = ns * 0.55
        if email_eq:
            score += 0.45
        if phone_eq:
            score += 0.35
        if email_conflict and phone_conflict:
            return None
        score = min(score, 1.0)
        if score < self.threshold:
            return None
        return Match(a.key, b.key, round(score, 3), evidence)

    def resolve(self, records: Iterable[Record]) -> list[Entity]:
        records = list(records)
        by_key = {r.key: r for r in records}
        blocks: dict[str, list[Record]] = defaultdict(list)
        for r in records:
            for k in self._blocks(r):
                blocks[k].append(r)

        seen: set[tuple[str, str]] = set()
        uf = _UnionFind()
        for r in records:
            uf.find(r.key)
        matches: list[Match] = []
        for group in blocks.values():
            for a, b in combinations(group, 2):
                pair = tuple(sorted((a.key, b.key)))
                if pair in seen or a.source == b.source and a.id == b.id:
                    continue
                seen.add(pair)
                m = self.score(a, b)
                if m:
                    matches.append(m)
                    uf.union(a.key, b.key)

        clusters: dict[str, list[Record]] = defaultdict(list)
        for r in records:
            clusters[uf.find(r.key)].append(r)
        cluster_matches: dict[str, list[Match]] = defaultdict(list)
        for m in matches:
            cluster_matches[uf.find(m.a)].append(m)

        entities = []
        for i, root in enumerate(sorted(clusters), 1):
            entities.append(Entity(f"E{i:04d}", clusters[root], cluster_matches.get(root, [])))
        return entities
