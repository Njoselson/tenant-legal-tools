#!/usr/bin/env python3
"""
CLI tool for retrieving terms and sentences from Qdrant vector database and ArangoDB.

Supports:
- Semantic search: Input a sentence/paragraph, get similar chunks from Qdrant
- Keyword search: Search entities and quotes in ArangoDB
- Direct ID lookup: Retrieve by chunk_id, entity_id, source_id, etc.

Usage:
    # Semantic search (primary use case)
    python -m tenant_legal_guidance.scripts.retrieve \
      --semantic "My landlord won't fix the mold in my bathroom" \
      --top-k 10

    # Keyword search for entities
    python -m tenant_legal_guidance.scripts.retrieve \
      --keyword "warranty of habitability" \
      --entity-type law \
      --top-k 20

    # Search quotes
    python -m tenant_legal_guidance.scripts.retrieve \
      --quotes "habitability" \
      --top-k 10

    # Direct ID lookup
    python -m tenant_legal_guidance.scripts.retrieve --chunk-id "550e8400:5"
    python -m tenant_legal_guidance.scripts.retrieve --entity-id "law:warranty_of_habitability"
    python -m tenant_legal_guidance.scripts.retrieve --source-id "550e8400-e29b-41d4-a716-446655440000"
    python -m tenant_legal_guidance.scripts.retrieve --chunks-by-entity "law:warranty_of_habitability"

    # Output format options
    python -m tenant_legal_guidance.scripts.retrieve \
      --semantic "query" \
      --format table  # or json, text
"""

import argparse
import json
import sys
from typing import Any

from rich.console import Console
from rich.table import Table

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import EntityType
from tenant_legal_guidance.services.embeddings import EmbeddingsService
from tenant_legal_guidance.services.vector_store import QdrantVectorStore


class RetrievalCLI:
    """CLI for retrieving data from Qdrant and ArangoDB."""

    def __init__(self):
        self.console = Console()
        self.vector_store = None
        self.knowledge_graph = None
        self.embeddings_svc = None

    def _init_connections(self):
        """Initialize connections to Qdrant and ArangoDB."""
        try:
            self.vector_store = QdrantVectorStore()
        except Exception as e:
            self.console.print(
                f"[red]Error connecting to Qdrant: {e}[/red]\n"
                "[yellow]Please ensure Qdrant is running and accessible.[/yellow]"
            )
            sys.exit(1)

        try:
            self.knowledge_graph = ArangoDBGraph()
        except Exception as e:
            self.console.print(
                f"[red]Error connecting to ArangoDB: {e}[/red]\n"
                "[yellow]Please ensure ArangoDB is running and accessible.[/yellow]"
            )
            sys.exit(1)

        try:
            self.embeddings_svc = EmbeddingsService()
        except Exception as e:
            self.console.print(
                f"[red]Error initializing embeddings service: {e}[/red]\n"
                "[yellow]Please check that sentence-transformers is properly installed.[/yellow]"
            )
            sys.exit(1)

    def semantic_search(self, query: str, top_k: int, output_format: str) -> None:
        """Perform semantic search using vector similarity."""
        if not query or not query.strip():
            self.console.print("[red]Error: Query cannot be empty.[/red]")
            sys.exit(1)

        if top_k <= 0:
            self.console.print("[red]Error: top-k must be greater than 0.[/red]")
            sys.exit(1)

        if not self.vector_store:
            self._init_connections()

        try:
            # Create embedding for query
            query_embedding = self.embeddings_svc.embed([query])[0]

            # Search Qdrant
            results = self.vector_store.search(query_embedding, top_k=top_k)

            if not results:
                self.console.print("[yellow]No similar chunks found.[/yellow]")
                return

            self._format_chunk_results(results, query, "semantic", output_format)

        except Exception as e:
            self.console.print(f"[red]Error performing semantic search: {e}[/red]")
            if "connection" in str(e).lower() or "timeout" in str(e).lower():
                self.console.print("[yellow]Please check that Qdrant is running and accessible.[/yellow]")
            sys.exit(1)

    def keyword_search_entities(
        self, query: str, entity_type: str | None, jurisdiction: str | None, top_k: int, output_format: str
    ) -> None:
        """Search entities in ArangoDB using keyword search."""
        if not query or not query.strip():
            self.console.print("[red]Error: Query cannot be empty.[/red]")
            sys.exit(1)

        if top_k <= 0:
            self.console.print("[red]Error: top-k must be greater than 0.[/red]")
            sys.exit(1)

        if not self.knowledge_graph:
            self._init_connections()

        try:
            # Convert entity type string to EntityType enum if provided
            entity_types = None
            if entity_type:
                try:
                    entity_types = [EntityType(entity_type.lower())]
                except ValueError:
                    valid_types = [e.value for e in EntityType]
                    self.console.print(
                        f"[red]Invalid entity type: {entity_type}[/red]\n"
                        f"[yellow]Valid types: {', '.join(valid_types)}[/yellow]"
                    )
                    sys.exit(1)

            # Search entities
            entities = self.knowledge_graph.search_entities_by_text(
                query, types=entity_types, jurisdiction=jurisdiction, limit=top_k
            )

            if not entities:
                self.console.print("[yellow]No entities found.[/yellow]")
                return

            self._format_entity_results(entities, query, output_format)

        except Exception as e:
            self.console.print(f"[red]Error searching entities: {e}[/red]")
            if "connection" in str(e).lower() or "timeout" in str(e).lower():
                self.console.print("[yellow]Please check that ArangoDB is running and accessible.[/yellow]")
            sys.exit(1)

    def keyword_search_quotes(self, query: str, top_k: int, output_format: str) -> None:
        """Search quotes in ArangoDB."""
        if not query or not query.strip():
            self.console.print("[red]Error: Query cannot be empty.[/red]")
            sys.exit(1)

        if top_k <= 0:
            self.console.print("[red]Error: top-k must be greater than 0.[/red]")
            sys.exit(1)

        if not self.knowledge_graph:
            self._init_connections()

        try:
            # Query quotes collection using AQL
            aql = """
            FOR quote IN quotes
                FILTER quote.quote_sha256 != null
                LIMIT @limit
                RETURN quote
            """
            cursor = self.knowledge_graph.db.aql.execute(aql, bind_vars={"limit": top_k * 10})

            quotes = []
            for quote_doc in cursor:
                quote_id = quote_doc.get("_key", "")
                source_id = quote_doc.get("source_id", "")
                start_offset = quote_doc.get("start_offset", 0)
                end_offset = quote_doc.get("end_offset", 0)

                # Get quote text snippet
                snippet = self.knowledge_graph.get_quote_snippet(quote_id)
                if snippet:
                    quote_text = snippet.get("text", "")
                    # Simple text matching (case-insensitive)
                    if query.lower() in quote_text.lower():
                        quotes.append(
                            {
                                "quote_id": quote_id,
                                "source_id": source_id,
                                "text": quote_text,
                                "start_offset": start_offset,
                                "end_offset": end_offset,
                            }
                        )
                        if len(quotes) >= top_k:
                            break

            if not quotes:
                self.console.print("[yellow]No quotes found.[/yellow]")
                return

            self._format_quote_results(quotes, query, output_format)

        except Exception as e:
            self.console.print(f"[red]Error searching quotes: {e}[/red]")
            if "connection" in str(e).lower() or "timeout" in str(e).lower():
                self.console.print("[yellow]Please check that ArangoDB is running and accessible.[/yellow]")
            sys.exit(1)

    def lookup_chunk_by_id(self, chunk_id: str, output_format: str) -> None:
        """Retrieve a chunk by its ID."""
        if not chunk_id or not chunk_id.strip():
            self.console.print("[red]Error: Chunk ID cannot be empty.[/red]")
            sys.exit(1)

        if not self.vector_store:
            self._init_connections()

        try:
            results = self.vector_store.search_by_id(chunk_id)
            if not results:
                self.console.print(f"[yellow]Chunk not found: {chunk_id}[/yellow]")
                return

            self._format_chunk_results(results, f"chunk_id={chunk_id}", "lookup", output_format)

        except Exception as e:
            self.console.print(f"[red]Error retrieving chunk: {e}[/red]")
            if "connection" in str(e).lower() or "timeout" in str(e).lower():
                self.console.print("[yellow]Please check that Qdrant is running and accessible.[/yellow]")
            sys.exit(1)

    def lookup_entity_by_id(self, entity_id: str, output_format: str) -> None:
        """Retrieve an entity by its ID."""
        if not entity_id or not entity_id.strip():
            self.console.print("[red]Error: Entity ID cannot be empty.[/red]")
            sys.exit(1)

        if not self.knowledge_graph:
            self._init_connections()

        try:
            entity = self.knowledge_graph.get_entity(entity_id)
            if not entity:
                self.console.print(f"[yellow]Entity not found: {entity_id}[/yellow]")
                return

            self._format_entity_results([entity], f"entity_id={entity_id}", output_format)

        except Exception as e:
            self.console.print(f"[red]Error retrieving entity: {e}[/red]")
            if "connection" in str(e).lower() or "timeout" in str(e).lower():
                self.console.print("[yellow]Please check that ArangoDB is running and accessible.[/yellow]")
            sys.exit(1)

    def lookup_chunks_by_source(self, source_id: str, output_format: str) -> None:
        """Retrieve all chunks for a source."""
        if not source_id or not source_id.strip():
            self.console.print("[red]Error: Source ID cannot be empty.[/red]")
            sys.exit(1)

        if not self.vector_store:
            self._init_connections()

        try:
            chunks = self.vector_store.get_chunks_by_source(source_id)
            if not chunks:
                self.console.print(f"[yellow]No chunks found for source: {source_id}[/yellow]")
                return

            # Convert to format expected by formatter
            results = []
            for chunk in chunks:
                results.append(
                    {
                        "id": chunk.get("id", ""),
                        "score": 1.0,  # No score for direct lookup
                        "payload": chunk.get("payload", {}),
                    }
                )

            self._format_chunk_results(results, f"source_id={source_id}", "lookup", output_format)

        except Exception as e:
            self.console.print(f"[red]Error retrieving chunks by source: {e}[/red]")
            if "connection" in str(e).lower() or "timeout" in str(e).lower():
                self.console.print("[yellow]Please check that Qdrant is running and accessible.[/yellow]")
            sys.exit(1)

    def lookup_chunks_by_entity(self, entity_id: str, output_format: str) -> None:
        """Retrieve all chunks that mention an entity."""
        if not entity_id or not entity_id.strip():
            self.console.print("[red]Error: Entity ID cannot be empty.[/red]")
            sys.exit(1)

        if not self.vector_store:
            self._init_connections()

        try:
            chunks = self.vector_store.get_chunks_by_entity(entity_id)
            if not chunks:
                self.console.print(f"[yellow]No chunks found for entity: {entity_id}[/yellow]")
                return

            # Convert to format expected by formatter
            results = []
            for chunk in chunks:
                results.append(
                    {
                        "id": chunk.get("id", ""),
                        "score": 1.0,  # No score for direct lookup
                        "payload": chunk.get("payload", {}),
                    }
                )

            self._format_chunk_results(results, f"entity_id={entity_id}", "lookup", output_format)

        except Exception as e:
            self.console.print(f"[red]Error retrieving chunks by entity: {e}[/red]")
            if "connection" in str(e).lower() or "timeout" in str(e).lower():
                self.console.print("[yellow]Please check that Qdrant is running and accessible.[/yellow]")
            sys.exit(1)

    def _format_chunk_results(
        self, results: list[dict[str, Any]], query: str, search_type: str, output_format: str
    ) -> None:
        """Format and display chunk results."""
        if output_format == "json":
            output = {
                "query": query,
                "search_type": search_type,
                "count": len(results),
                "results": [
                    {
                        "id": r.get("id", ""),
                        "score": r.get("score", 0.0),
                        "chunk_id": r.get("payload", {}).get("chunk_id", ""),
                        "text": r.get("payload", {}).get("text", "")[:500] + "..."
                        if len(r.get("payload", {}).get("text", "")) > 500
                        else r.get("payload", {}).get("text", ""),
                        "source_id": r.get("payload", {}).get("source_id", ""),
                        "doc_title": r.get("payload", {}).get("doc_title", ""),
                        "entities": r.get("payload", {}).get("entities", []),
                        "jurisdiction": r.get("payload", {}).get("jurisdiction", ""),
                    }
                    for r in results
                ],
            }
            print(json.dumps(output, indent=2))

        elif output_format == "table":
            table = Table(title=f"Chunk Results ({search_type} search)", show_header=True, header_style="bold magenta")
            table.add_column("#", style="dim", width=4)
            table.add_column("Score", justify="right", width=8)
            table.add_column("Text (excerpt)", width=60)
            table.add_column("Source", width=30)
            table.add_column("Entities", width=20)

            for idx, r in enumerate(results, 1):
                payload = r.get("payload", {})
                text = payload.get("text", "")
                text_excerpt = (text[:200] + "...") if len(text) > 200 else text
                score = r.get("score", 0.0)
                doc_title = payload.get("doc_title", "") or payload.get("source_id", "")
                entities = ", ".join(payload.get("entities", [])[:3])
                if len(payload.get("entities", [])) > 3:
                    entities += "..."

                table.add_row(
                    str(idx),
                    f"{score:.3f}" if score > 0 else "-",
                    text_excerpt,
                    doc_title[:30],
                    entities[:20] or "-",
                )

            self.console.print(table)

        else:  # text format
            print(f"Found {len(results)} chunks ({search_type} search):\n")
            for idx, r in enumerate(results, 1):
                payload = r.get("payload", {})
                score = r.get("score", 0.0)
                text = payload.get("text", "")
                print(f"{idx}. [Score: {score:.3f}] {payload.get('doc_title', 'Unknown')}")
                print(f"   {text[:300]}...")
                print(f"   Entities: {', '.join(payload.get('entities', [])[:5])}")
                print()

    def _format_entity_results(
        self, entities: list[Any], query: str, output_format: str
    ) -> None:
        """Format and display entity results."""
        if output_format == "json":
            output = {
                "query": query,
                "count": len(entities),
                "results": [
                    {
                        "id": e.id,
                        "name": e.name,
                        "type": e.entity_type.value if hasattr(e.entity_type, "value") else str(e.entity_type),
                        "description": e.description or "",
                        "jurisdiction": (e.source_metadata.jurisdiction if e.source_metadata else None) or "",
                        "best_quote": e.best_quote if isinstance(e.best_quote, dict) else (e.best_quote.model_dump() if e.best_quote else None),
                    }
                    for e in entities
                ],
            }
            print(json.dumps(output, indent=2))

        elif output_format == "table":
            table = Table(title="Entity Results", show_header=True, header_style="bold magenta")
            table.add_column("#", style="dim", width=4)
            table.add_column("ID", width=30)
            table.add_column("Name", width=40)
            table.add_column("Type", width=15)
            table.add_column("Description", width=50)

            for idx, e in enumerate(entities, 1):
                desc = (e.description or "")[:100] + "..." if len(e.description or "") > 100 else (e.description or "")
                table.add_row(
                    str(idx),
                    e.id,
                    e.name[:40],
                    e.entity_type.value if hasattr(e.entity_type, "value") else str(e.entity_type),
                    desc,
                )

            self.console.print(table)

        else:  # text format
            print(f"Found {len(entities)} entities:\n")
            for idx, e in enumerate(entities, 1):
                print(f"{idx}. {e.name} ({e.entity_type.value if hasattr(e.entity_type, 'value') else e.entity_type})")
                print(f"   ID: {e.id}")
                if e.description:
                    print(f"   Description: {e.description[:200]}...")
                if e.source_metadata and e.source_metadata.jurisdiction:
                    print(f"   Jurisdiction: {e.source_metadata.jurisdiction}")
                print()

    def _format_quote_results(self, quotes: list[dict[str, Any]], query: str, output_format: str) -> None:
        """Format and display quote results."""
        if output_format == "json":
            output = {"query": query, "count": len(quotes), "results": quotes}
            print(json.dumps(output, indent=2))

        elif output_format == "table":
            table = Table(title="Quote Results", show_header=True, header_style="bold magenta")
            table.add_column("#", style="dim", width=4)
            table.add_column("Quote ID", width=30)
            table.add_column("Text", width=70)
            table.add_column("Source ID", width=30)

            for idx, q in enumerate(quotes, 1):
                text = (q.get("text", "")[:200] + "...") if len(q.get("text", "")) > 200 else q.get("text", "")
                table.add_row(
                    str(idx),
                    q.get("quote_id", ""),
                    text,
                    q.get("source_id", "")[:30],
                )

            self.console.print(table)

        else:  # text format
            print(f"Found {len(quotes)} quotes:\n")
            for idx, q in enumerate(quotes, 1):
                print(f"{idx}. Quote ID: {q.get('quote_id', '')}")
                print(f"   Source: {q.get('source_id', '')}")
                print(f"   Text: {q.get('text', '')[:300]}...")
                print()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Retrieve terms and sentences from Qdrant and ArangoDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Mutually exclusive query type group
    query_group = parser.add_mutually_exclusive_group(required=True)
    query_group.add_argument("--semantic", type=str, help="Semantic search: input sentence/paragraph")
    query_group.add_argument("--keyword", type=str, help="Keyword search for entities")
    query_group.add_argument("--quotes", type=str, help="Search quotes collection")
    query_group.add_argument("--chunk-id", type=str, help="Lookup chunk by ID")
    query_group.add_argument("--entity-id", type=str, help="Lookup entity by ID")
    query_group.add_argument("--source-id", type=str, help="Get all chunks for a source ID")
    query_group.add_argument(
        "--chunks-by-entity", type=str, help="Get all chunks that mention an entity ID"
    )

    # Optional filters
    parser.add_argument(
        "--entity-type",
        type=str,
        help="Filter entities by type (e.g., 'law', 'remedy', 'legal_procedure')",
    )
    parser.add_argument("--jurisdiction", type=str, help="Filter by jurisdiction")
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of results to return (default: 10, must be > 0)",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table", "text"],
        default="json",
        help="Output format (default: json)",
    )

    args = parser.parse_args()

    # Validate top-k
    if args.top_k <= 0:
        parser.error("--top-k must be greater than 0")

    cli = RetrievalCLI()

    try:
        if args.semantic:
            cli.semantic_search(args.semantic, args.top_k, args.format)
        elif args.keyword:
            cli.keyword_search_entities(args.keyword, args.entity_type, args.jurisdiction, args.top_k, args.format)
        elif args.quotes:
            cli.keyword_search_quotes(args.quotes, args.top_k, args.format)
        elif args.chunk_id:
            cli.lookup_chunk_by_id(args.chunk_id, args.format)
        elif args.entity_id:
            cli.lookup_entity_by_id(args.entity_id, args.format)
        elif args.source_id:
            cli.lookup_chunks_by_source(args.source_id, args.format)
        elif args.chunks_by_entity:
            cli.lookup_chunks_by_entity(args.chunks_by_entity, args.format)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

