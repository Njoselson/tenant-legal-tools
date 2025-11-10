import logging

import pytest

from tenant_legal_guidance.api import routes
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.relationships import RelationshipType


class FakeCursor(list):
    pass


class FakeAQL:
    def __init__(self, docs):
        self.docs = docs

    def execute(self, _query, bind_vars=None):
        # Emulate LIMIT @offset, @limit over the docs
        offset = int((bind_vars or {}).get("offset", 0))
        limit = int((bind_vars or {}).get("limit", len(self.docs)))
        return FakeCursor(self.docs[offset : offset + limit])


class FakeDB:
    def __init__(self, docs):
        self.docs = docs
        self.aql = FakeAQL(docs)
        self._collections = {}

    def has_collection(self, name: str) -> bool:
        return name in self._collections

    def collection(self, name: str):
        return self._collections[name]

    def register_collection(self, name: str, coll):
        self._collections[name] = coll


class FakeEdgeCollection:
    def __init__(self):
        self.added_indexes = []

    def add_index(self, spec):
        # Capture index specifications
        self.added_indexes.append(spec)


def make_fake_system_with_docs(num_docs: int = 5):
    # Prepare synthetic node docs
    docs = []
    for i in range(num_docs):
        docs.append(
            {
                "_key": f"law:{i}",
                "type": "law",
                "name": f"Law {i}",
                "description": f"Desc {i}",
                "jurisdiction": "NYC" if i % 2 == 0 else "SF",
                "source_metadata": {},
            }
        )

    class FakeKG:
        def __init__(self):
            self.db = FakeDB(docs)

        def get_relationships_among(self, node_ids):
            return []

    class FakeSystem:
        def __init__(self):
            self.knowledge_graph = FakeKG()

    return FakeSystem()


@pytest.mark.asyncio
async def test_graph_data_pagination_basic():
    system = make_fake_system_with_docs(7)
    # Page 1
    result1 = await routes.get_graph_data(system=system, offset=0, limit=3)
    assert len(result1["nodes"]) == 3
    assert result1["next_cursor"] == 3
    # Page 2
    result2 = await routes.get_graph_data(
        system=system, cursor=str(result1["next_cursor"]), limit=3
    )
    assert len(result2["nodes"]) == 3
    assert result2["next_cursor"] == 6
    # Page 3
    result3 = await routes.get_graph_data(
        system=system, cursor=str(result2["next_cursor"]), limit=3
    )
    assert len(result3["nodes"]) == 1
    assert result3.get("next_cursor") is None


def test_edge_unique_index_created():
    # Build a graph instance without running __init__
    graph: ArangoDBGraph = ArangoDBGraph.__new__(ArangoDBGraph)  # type: ignore
    graph.logger = logging.getLogger(__name__)

    # Fake DB with edge collections for all relationship types
    docs = []
    fdb = FakeDB(docs)
    for rel in RelationshipType:
        coll = FakeEdgeCollection()
        fdb.register_collection(rel.name.lower(), coll)
    # has_collection should report True for all edges
    original_has = fdb.has_collection

    def patched_has(name: str) -> bool:
        return True if name in fdb._collections else original_has(name)

    fdb.has_collection = patched_has  # type: ignore

    graph.db = fdb

    # Call index initialization
    ArangoDBGraph._init_indexes(graph)

    # Verify each edge collection received a unique index on (_from,_to,type)
    for rel in RelationshipType:
        coll = fdb.collection(rel.name.lower())
        assert any(
            idx.get("unique") is True and idx.get("fields") == ["_from", "_to", "type"]
            for idx in coll.added_indexes
        )
