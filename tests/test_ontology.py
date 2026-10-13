import json
from pathlib import Path

from ontology_lite import ObjectGraph, Record, Resolver, similarity
from ontology_lite.cli import build

DATA = Path(__file__).parent.parent / "examples" / "data.json"


def test_similarity_basics():
    assert similarity("Maria", "María") == 1.0
    assert similarity("martha", "marhta") > 0.9
    assert similarity("abc", "xyz") < 0.5


def test_merge_on_shared_email_across_name_formats():
    recs = [
        Record("crm", "1", {"name": "John Smith", "email": "j@x.com"}),
        Record("mail", "a", {"name": "Smith, John", "email": "j@x.com"}),
    ]
    ents = Resolver().resolve(recs)
    assert len(ents) == 1 and len(ents[0].members) == 2
    assert ents[0].matches[0].evidence["email"] == "exact"


def test_same_name_different_identifiers_not_merged():
    recs = [
        Record("crm", "1", {"name": "John Smith", "email": "a@x.com", "phone": "555-010-2200"}),
        Record("crm", "3", {"name": "John Smith", "email": "b@y.org", "phone": "555-999-1234"}),
    ]
    assert len(Resolver().resolve(recs)) == 2


def test_name_alone_is_not_enough():
    recs = [Record("a", "1", {"name": "Wei Chen"}), Record("b", "2", {"name": "Wei Chen"})]
    assert len(Resolver().resolve(recs)) == 2


def test_transitive_merge_through_phone():
    recs = [
        Record("crm", "1", {"name": "John Smith", "email": "j@x.com", "phone": "555-010-2200"}),
        Record("mail", "a", {"name": "John Smith", "email": "j@x.com"}),
        Record("bank", "9", {"name": "J. Smith", "phone": "(555) 010 2200"}),
    ]
    assert len(Resolver().resolve(recs)) == 1


def test_graph_path_components_betweenness():
    g = ObjectGraph()
    for n in "ABCDE":
        g.add_object(n, "T")
    g.add_link("A", "B", "x")
    g.add_link("B", "C", "x")
    g.add_link("C", "D", "x")
    assert g.shortest_path("A", "D") == ["A", "B", "C", "D"]
    assert g.shortest_path("A", "E") is None
    assert [len(c) for c in g.components()] == [4, 1]
    bc = g.betweenness()
    assert bc["B"] == bc["C"] == 2.0 and bc["A"] == 0.0
    assert g.within("A", 2) == {"B": 1, "C": 2}


def test_end_to_end_example():
    entities, graph = build(json.loads(DATA.read_text()))
    assert sum(len(e.members) for e in entities) == 11
    assert len(entities) == 7  # John Smith(3->1), Maria(2->1), Wei(2->1), plus 4 singles incl. the other John
    names = [e.canonical("name") for e in entities]
    assert names.count("John Smith") == 2  # the two different John Smiths stay separate
    assert graph.components()
