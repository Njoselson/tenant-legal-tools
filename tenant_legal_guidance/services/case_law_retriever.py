"""
Case law specific retrieval methods for finding precedents, holdings, and related cases.
"""

import logging

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import EntityType
from tenant_legal_guidance.services.embeddings import EmbeddingsService
from tenant_legal_guidance.services.vector_store import QdrantVectorStore


class CaseLawRetriever:
    """Specialized retrieval methods for case law documents."""
    
    def __init__(self, knowledge_graph: ArangoDBGraph, vector_store: QdrantVectorStore):
        self.knowledge_graph = knowledge_graph
        self.vector_store = vector_store
        self.embeddings_svc = EmbeddingsService()
        self.logger = logging.getLogger(__name__)
    
    def find_precedent_cases(
        self, 
        issue: str, 
        jurisdiction: str | None = None,
        court: str | None = None,
        limit: int = 20
    ) -> list[dict]:
        """
        Find similar cases by legal issue and jurisdiction.
        
        Args:
            issue: Legal issue to search for (e.g., "rent reduction for habitability")
            jurisdiction: Optional jurisdiction filter (e.g., "NYC", "New York State")
            court: Optional court filter (e.g., "NYC Housing Court")
            limit: Maximum number of cases to return
            
        Returns:
            List of case documents with similarity scores
        """
        try:
            # Create query embedding
            query_embedding = self.embeddings_svc.embed([issue])[0]
            
            # Build filter for court opinions
            filter_payload = {"document_type": "court_opinion"}
            if jurisdiction:
                filter_payload["jurisdiction"] = jurisdiction
            if court:
                filter_payload["court"] = court
            
            # Search for similar chunks
            chunk_results = self.vector_store.search(
                query_embedding=query_embedding,
                top_k=limit * 3,  # Get more chunks, then deduplicate by case
                filter_payload=filter_payload
            )
            
            # Group chunks by case document
            cases_by_document = {}
            for chunk in chunk_results:
                case_doc_id = chunk["payload"].get("doc_metadata", {}).get("case_document_id")
                if case_doc_id:
                    if case_doc_id not in cases_by_document:
                        cases_by_document[case_doc_id] = {
                            "case_document_id": case_doc_id,
                            "case_name": chunk["payload"].get("case_name"),
                            "court": chunk["payload"].get("court"),
                            "jurisdiction": chunk["payload"].get("jurisdiction"),
                            "decision_date": chunk["payload"].get("decision_date"),
                            "chunks": [],
                            "max_score": 0.0
                        }
                    
                    cases_by_document[case_doc_id]["chunks"].append(chunk)
                    cases_by_document[case_doc_id]["max_score"] = max(
                        cases_by_document[case_doc_id]["max_score"], 
                        chunk["score"]
                    )
            
            # Sort by relevance score and return top cases
            sorted_cases = sorted(
                cases_by_document.values(),
                key=lambda x: x["max_score"],
                reverse=True
            )
            
            return sorted_cases[:limit]
            
        except Exception as e:
            self.logger.error(f"Failed to find precedent cases: {e}", exc_info=True)
            return []
    
    def get_case_holdings(self, case_document_id: str) -> list[str]:
        """
        Get all holdings from a specific case.
        
        Args:
            case_document_id: ID of the case document entity
            
        Returns:
            List of legal holdings
        """
        try:
            # Get the case document entity
            case_entity = self.knowledge_graph.get_entity(case_document_id)
            if not case_entity or case_entity.get("entity_type") != EntityType.CASE_DOCUMENT:
                return []
            
            # Extract holdings from the entity
            holdings = case_entity.get("holdings", [])
            if isinstance(holdings, list):
                return holdings
            
            return []
            
        except Exception as e:
            self.logger.error(f"Failed to get case holdings: {e}", exc_info=True)
            return []
    
    def find_cases_by_party(self, party_name: str, limit: int = 20) -> list[dict]:
        """
        Find all cases involving a specific party.
        
        Args:
            party_name: Name of the party (plaintiff or defendant)
            limit: Maximum number of cases to return
            
        Returns:
            List of cases involving the party
        """
        try:
            # Search for chunks containing the party name
            query_embedding = self.embeddings_svc.embed([party_name])[0]
            
            chunk_results = self.vector_store.search(
                query_embedding=query_embedding,
                top_k=limit * 3,
                filter_payload={"document_type": "court_opinion"}
            )
            
            # Filter chunks that actually mention the party
            relevant_chunks = []
            party_lower = party_name.lower()
            
            for chunk in chunk_results:
                chunk_text = chunk["payload"].get("text", "").lower()
                case_name = chunk["payload"].get("case_name", "").lower()
                
                # Check if party is mentioned in text or case name
                if (party_lower in chunk_text or 
                    party_lower in case_name or
                    any(party_lower in p.lower() for p in chunk["payload"].get("parties", {}).values())):
                    relevant_chunks.append(chunk)
            
            # Group by case document
            cases_by_document = {}
            for chunk in relevant_chunks:
                case_doc_id = chunk["payload"].get("doc_metadata", {}).get("case_document_id")
                if case_doc_id:
                    if case_doc_id not in cases_by_document:
                        cases_by_document[case_doc_id] = {
                            "case_document_id": case_doc_id,
                            "case_name": chunk["payload"].get("case_name"),
                            "court": chunk["payload"].get("court"),
                            "jurisdiction": chunk["payload"].get("jurisdiction"),
                            "decision_date": chunk["payload"].get("decision_date"),
                            "parties": chunk["payload"].get("parties", {}),
                            "chunks": [],
                            "max_score": 0.0
                        }
                    
                    cases_by_document[case_doc_id]["chunks"].append(chunk)
                    cases_by_document[case_doc_id]["max_score"] = max(
                        cases_by_document[case_doc_id]["max_score"], 
                        chunk["score"]
                    )
            
            # Sort by relevance and return
            sorted_cases = sorted(
                cases_by_document.values(),
                key=lambda x: x["max_score"],
                reverse=True
            )
            
            return sorted_cases[:limit]
            
        except Exception as e:
            self.logger.error(f"Failed to find cases by party: {e}", exc_info=True)
            return []
    
    def find_cases_by_court(self, court_name: str, limit: int = 20) -> list[dict]:
        """
        Find all cases from a specific court.
        
        Args:
            court_name: Name of the court (e.g., "NYC Housing Court")
            limit: Maximum number of cases to return
            
        Returns:
            List of cases from the court
        """
        try:
            # Get all chunks from the specified court
            chunks = self.vector_store.get_chunks_by_source("")  # Get all chunks
            court_chunks = [
                chunk for chunk in chunks 
                if chunk["payload"].get("court", "").lower() == court_name.lower()
            ]
            
            # Group by case document
            cases_by_document = {}
            for chunk in court_chunks:
                case_doc_id = chunk["payload"].get("doc_metadata", {}).get("case_document_id")
                if case_doc_id:
                    if case_doc_id not in cases_by_document:
                        cases_by_document[case_doc_id] = {
                            "case_document_id": case_doc_id,
                            "case_name": chunk["payload"].get("case_name"),
                            "court": chunk["payload"].get("court"),
                            "jurisdiction": chunk["payload"].get("jurisdiction"),
                            "decision_date": chunk["payload"].get("decision_date"),
                            "chunk_count": 0
                        }
                    
                    cases_by_document[case_doc_id]["chunk_count"] += 1
            
            # Sort by decision date (most recent first)
            sorted_cases = sorted(
                cases_by_document.values(),
                key=lambda x: x.get("decision_date", ""),
                reverse=True
            )
            
            return sorted_cases[:limit]
            
        except Exception as e:
            self.logger.error(f"Failed to find cases by court: {e}", exc_info=True)
            return []
    
    def find_cases_by_citation(self, citation: str, limit: int = 20) -> list[dict]:
        """
        Find cases that cite a specific law or case.
        
        Args:
            citation: Citation to search for (e.g., "RSC §26-504")
            limit: Maximum number of cases to return
            
        Returns:
            List of cases that cite the specified law/case
        """
        try:
            # Search for chunks containing the citation
            query_embedding = self.embeddings_svc.embed([citation])[0]
            
            chunk_results = self.vector_store.search(
                query_embedding=query_embedding,
                top_k=limit * 3,
                filter_payload={"document_type": "court_opinion"}
            )
            
            # Filter chunks that actually contain the citation
            relevant_chunks = []
            citation_lower = citation.lower()
            
            for chunk in chunk_results:
                chunk_text = chunk["payload"].get("text", "").lower()
                citations = chunk["payload"].get("citations", [])
                
                # Check if citation is mentioned in text or citations list
                if (citation_lower in chunk_text or 
                    any(citation_lower in c.lower() for c in citations)):
                    relevant_chunks.append(chunk)
            
            # Group by case document
            cases_by_document = {}
            for chunk in relevant_chunks:
                case_doc_id = chunk["payload"].get("doc_metadata", {}).get("case_document_id")
                if case_doc_id:
                    if case_doc_id not in cases_by_document:
                        cases_by_document[case_doc_id] = {
                            "case_document_id": case_doc_id,
                            "case_name": chunk["payload"].get("case_name"),
                            "court": chunk["payload"].get("court"),
                            "jurisdiction": chunk["payload"].get("jurisdiction"),
                            "decision_date": chunk["payload"].get("decision_date"),
                            "citations": chunk["payload"].get("citations", []),
                            "chunks": [],
                            "max_score": 0.0
                        }
                    
                    cases_by_document[case_doc_id]["chunks"].append(chunk)
                    cases_by_document[case_doc_id]["max_score"] = max(
                        cases_by_document[case_doc_id]["max_score"], 
                        chunk["score"]
                    )
            
            # Sort by relevance and return
            sorted_cases = sorted(
                cases_by_document.values(),
                key=lambda x: x["max_score"],
                reverse=True
            )
            
            return sorted_cases[:limit]
            
        except Exception as e:
            self.logger.error(f"Failed to find cases by citation: {e}", exc_info=True)
            return []
    
    def get_case_timeline(self, case_document_id: str) -> dict:
        """
        Get procedural timeline for a case.
        
        Args:
            case_document_id: ID of the case document entity
            
        Returns:
            Dictionary with procedural history and timeline
        """
        try:
            # Get the case document entity
            case_entity = self.knowledge_graph.get_entity(case_document_id)
            if not case_entity or case_entity.get("entity_type") != EntityType.CASE_DOCUMENT:
                return {}
            
            return {
                "case_name": case_entity.get("case_name"),
                "court": case_entity.get("court"),
                "docket_number": case_entity.get("docket_number"),
                "decision_date": case_entity.get("decision_date"),
                "procedural_history": case_entity.get("procedural_history"),
                "parties": case_entity.get("parties", {}),
                "holdings": case_entity.get("holdings", []),
                "citations": case_entity.get("citations", [])
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get case timeline: {e}", exc_info=True)
            return {}
    
    def search_case_law(
        self, 
        query: str, 
        filters: dict | None = None,
        limit: int = 20
    ) -> list[dict]:
        """
        General case law search with optional filters.
        
        Args:
            query: Search query
            filters: Optional filters (jurisdiction, court, date_range, etc.)
            limit: Maximum number of results
            
        Returns:
            List of matching cases
        """
        try:
            # Create query embedding
            query_embedding = self.embeddings_svc.embed([query])[0]
            
            # Build filter payload
            filter_payload = {"document_type": "court_opinion"}
            if filters:
                if "jurisdiction" in filters:
                    filter_payload["jurisdiction"] = filters["jurisdiction"]
                if "court" in filters:
                    filter_payload["court"] = filters["court"]
                # Add more filters as needed
            
            # Search for similar chunks
            chunk_results = self.vector_store.search(
                query_embedding=query_embedding,
                top_k=limit * 3,
                filter_payload=filter_payload
            )
            
            # Group by case document and return unique cases
            cases_by_document = {}
            for chunk in chunk_results:
                case_doc_id = chunk["payload"].get("doc_metadata", {}).get("case_document_id")
                if case_doc_id:
                    if case_doc_id not in cases_by_document:
                        cases_by_document[case_doc_id] = {
                            "case_document_id": case_doc_id,
                            "case_name": chunk["payload"].get("case_name"),
                            "court": chunk["payload"].get("court"),
                            "jurisdiction": chunk["payload"].get("jurisdiction"),
                            "decision_date": chunk["payload"].get("decision_date"),
                            "relevance_score": chunk["score"],
                            "matching_chunks": []
                        }
                    
                    cases_by_document[case_doc_id]["matching_chunks"].append({
                        "chunk_id": chunk["id"],
                        "score": chunk["score"],
                        "text_preview": chunk["payload"].get("text", "")[:200] + "..."
                    })
            
            # Sort by relevance and return
            sorted_cases = sorted(
                cases_by_document.values(),
                key=lambda x: x["relevance_score"],
                reverse=True
            )
            
            return sorted_cases[:limit]
            
        except Exception as e:
            self.logger.error(f"Failed to search case law: {e}", exc_info=True)
            return []
