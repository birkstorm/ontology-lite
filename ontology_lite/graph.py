"""A small typed object graph with link-analysis algorithms (no dependencies)."""

from __future__ import annotations

from collections import defaultdict, deque


class ObjectGraph:
    """Objects have a type and properties; links are typed and undirected for analysis."""

    def __init__(self):
        self.objects: dict[str, dict] = {}
        self.adj: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    def add_object(self, oid: str, otype: str, **props):
        self.objects[oid] = {"type": otype, **props}
        self.adj[oid]  # ensure node exists

    def add_link(self, a: str, b: str, link_type: str):
        for x in (a, b):
            if x not in self.objects:
                raise KeyError(f"unknown object {x!r}")
        self.adj[a][b].add(link_type)
        self.adj[b][a].add(link_type)

    def neighbors(self, oid: str) -> list[str]:
        return sorted(self.adj[oid])

    def degree(self, oid: str) -> int:
        return len(self.adj[oid])

    def shortest_path(self, src: str, dst: str) -> list[str] | None:
        if src == dst:
            return [src]
        prev = {src: None}
        queue = deque([src])
        while queue:
            cur = queue.popleft()
            for nxt in sorted(self.adj[cur]):
                if nxt not in prev:
                    prev[nxt] = cur
                    if nxt == dst:
                        path = [dst]
                        while prev[path[-1]] is not None:
                            path.append(prev[path[-1]])
                        return path[::-1]
                    queue.append(nxt)
        return None

    def within(self, oid: str, hops: int) -> dict[str, int]:
        """All objects reachable within `hops` links, with their distance."""
        dist = {oid: 0}
        queue = deque([oid])
        while queue:
            cur = queue.popleft()
            if dist[cur] == hops:
                continue
            for nxt in self.adj[cur]:
                if nxt not in dist:
                    dist[nxt] = dist[cur] + 1
                    queue.append(nxt)
        del dist[oid]
        return dist

    def components(self) -> list[set[str]]:
        seen, out = set(), []
        for start in self.objects:
            if start in seen:
                continue
            comp, stack = set(), [start]
            while stack:
                cur = stack.pop()
                if cur in comp:
                    continue
                comp.add(cur)
                stack.extend(self.adj[cur].keys() - comp)
            seen |= comp
            out.append(comp)
        return sorted(out, key=lambda c: (-len(c), sorted(c)[0]))

    def betweenness(self) -> dict[str, float]:
        """Brandes' algorithm: how often each object sits on shortest paths between others.

        High scores flag brokers/bridges between otherwise separate groups.
        """
        bc = dict.fromkeys(self.objects, 0.0)
        for s in self.objects:
            stack, preds = [], defaultdict(list)
            sigma = dict.fromkeys(self.objects, 0)
            sigma[s] = 1
            dist = dict.fromkeys(self.objects, -1)
            dist[s] = 0
            queue = deque([s])
            while queue:
                v = queue.popleft()
                stack.append(v)
                for w in self.adj[v]:
                    if dist[w] < 0:
                        dist[w] = dist[v] + 1
                        queue.append(w)
                    if dist[w] == dist[v] + 1:
                        sigma[w] += sigma[v]
                        preds[w].append(v)
            delta = dict.fromkeys(self.objects, 0.0)
            while stack:
                w = stack.pop()
                for v in preds[w]:
                    delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
                if w != s:
                    bc[w] += delta[w]
        return {k: v / 2 for k, v in bc.items()}  # undirected: each pair counted twice

    def communities(self, max_iter: int = 20) -> list[set[str]]:
        """Deterministic label propagation."""
        label = {n: n for n in sorted(self.objects)}
        for _ in range(max_iter):
            changed = False
            for n in sorted(self.objects):
                if not self.adj[n]:
                    continue
                counts: dict[str, int] = defaultdict(int)
                for m in self.adj[n]:
                    counts[label[m]] += 1
                best = min(counts, key=lambda l: (-counts[l], l))
                if best != label[n]:
                    label[n], changed = best, True
            if not changed:
                break
        groups: dict[str, set[str]] = defaultdict(set)
        for n, l in label.items():
            groups[l].add(n)
        return sorted(groups.values(), key=lambda c: (-len(c), sorted(c)[0]))
