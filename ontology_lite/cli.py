"""Command line demo: resolve entities from JSON, build the graph, run link analysis."""

from __future__ import annotations

import argparse
import json
import sys

from .graph import ObjectGraph
from .resolve import Record, Resolver


def build(data: dict, threshold: float = 0.85):
    records = [Record(r["source"], r["id"], r.get("fields", {})) for r in data["records"]]
    entities = Resolver(threshold=threshold).resolve(records)
    key_to_entity = {m.key: e.id for e in entities for m in e.members}

    graph = ObjectGraph()
    for e in entities:
        graph.add_object(e.id, "Person", name=e.canonical("name"), email=e.canonical("email"))
    for link in data.get("links", []):
        a, b = key_to_entity[link["from"]], key_to_entity[link["to"]]
        if a != b:
            graph.add_link(a, b, link["type"])
    return entities, graph


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ontology-lite", description=__doc__)
    p.add_argument("data", help="JSON file with 'records' and 'links'")
    p.add_argument("--threshold", type=float, default=0.85)
    p.add_argument("--path", nargs=2, metavar=("FROM", "TO"),
                   help="entity ids (e.g. E0001 E0005) to find the shortest connection between")
    args = p.parse_args(argv)

    with open(args.data) as f:
        data = json.load(f)
    entities, graph = build(data, args.threshold)

    n_rec = sum(len(e.members) for e in entities)
    print(f"{n_rec} records -> {len(entities)} entities\n")
    for e in entities:
        name = e.canonical("name")
        srcs = ", ".join(m.key for m in e.members)
        print(f"{e.id}  {name:<16} [{srcs}]")
        for m in e.matches:
            print(f"        merge {m.a} ~ {m.b}  score={m.score}  evidence={m.evidence}")

    print("\nBrokers (betweenness):")
    bc = graph.betweenness()
    for oid, score in sorted(bc.items(), key=lambda kv: -kv[1])[:3]:
        print(f"  {oid} {graph.objects[oid]['name']:<16} {score:.2f}")

    print("\nCommunities:")
    for i, c in enumerate(graph.communities(), 1):
        print(f"  {i}: {', '.join(graph.objects[x]['name'] for x in sorted(c))}")

    if args.path:
        path = graph.shortest_path(*args.path)
        print("\nPath:", " -> ".join(graph.objects[x]["name"] for x in path) if path else "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
