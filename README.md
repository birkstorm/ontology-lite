# ontology-lite

Explainable **entity resolution** and **link analysis** over a typed object graph. Zero dependencies, pure Python 3.10+.

Real-world data is fragmented: the same person shows up as `John Smith` in the CRM, `Smith, John` in email, and `J. Smith` in bank records. This project merges those records into canonical entities, builds a graph of how those entities relate, and surfaces who the brokers and clusters are.

```
$ python -m ontology_lite examples/data.json --path E0001 E0007
11 records -> 7 entities

E0001  John Smith   [crm:1, mail:a, bank:77]
        merge crm:1 ~ mail:a    score=1.0    evidence={'name': 1.0, 'email': 'exact'}
        merge crm:1 ~ bank:77   score=0.872  evidence={'name': 0.95, 'phone': 'exact'}
...
Brokers (betweenness):
  E0006 Tomas Novak   8.50
Path: John Smith -> Wei Chen -> Tomas Novak -> Aisha Bello
```

## Design decisions

- **Every merge is auditable.** Each match records a score and the evidence behind it (which fields agreed, which conflicted). In high-stakes settings, "why did the system think these are the same person?" must always have an answer.
- **Precision over recall.** Name similarity alone can never trigger a merge (capped at 0.55 vs. a 0.85 threshold). Two different "John Smith"s stay separate unless a strong identifier (email, phone) corroborates. Conflicting identifiers veto a merge.
- **Blocking** keeps comparisons sub-quadratic: records are only compared if they share a name-prefix, email, or phone-suffix key.
- **Transitive clustering** via union-find, so `A~B` and `B~C` yields one entity even when `A` and `C` share nothing directly.
- **Link analysis from scratch:** BFS shortest path, k-hop expansion, connected components, Brandes' betweenness centrality (finds brokers), and deterministic label-propagation communities.

## Layout

| Path | What |
|---|---|
| `ontology_lite/resolve.py` | Jaro-Winkler, order-insensitive name matching, blocking, scoring, clustering |
| `ontology_lite/graph.py` | `ObjectGraph` + link-analysis algorithms |
| `ontology_lite/cli.py` | Demo CLI |
| `tests/` | pytest suite incl. end-to-end test |

## Run

```
pip install -e ".[dev]"
pytest
python -m ontology_lite examples/data.json
```

## Possible extensions

Pluggable per-field comparators, learned weights (Fellegi-Sunter / EM), incremental resolution as new records stream in, and property-level provenance on each canonical entity.
