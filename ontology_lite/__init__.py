"""ontology-lite: entity resolution and link analysis over an object graph."""

from .resolve import Record, Resolver, similarity
from .graph import ObjectGraph

__all__ = ["Record", "Resolver", "similarity", "ObjectGraph"]
