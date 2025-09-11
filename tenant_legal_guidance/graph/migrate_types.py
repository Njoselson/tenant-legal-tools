#!/usr/bin/env python3
import os
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph

if __name__ == "__main__":
    graph = ArangoDBGraph(
        host=os.getenv("ARANGO_HOST"),
        db_name=os.getenv("ARANGO_DB_NAME"),
        username=os.getenv("ARANGO_USERNAME"),
        password=os.getenv("ARANGO_PASSWORD"),
    )
    results = graph.migrate_types_to_values()
    print("Type migration summary:")
    for coll, count in results.items():
        print(f"  {coll}: {count}") 