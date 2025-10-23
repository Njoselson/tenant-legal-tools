"""
Concept grouping service using semantic similarity with embeddings.
Groups similar legal concepts as the knowledge graph grows.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import spacy

from tenant_legal_guidance.models.entities import EntityType, LegalEntity
from tenant_legal_guidance.models.relationships import LegalRelationship


@dataclass
class ConceptGroup:
    """Represents a group of similar concepts."""

    id: str
    name: str
    description: str
    entities: List[LegalEntity]
    similarity_score: float
    group_type: str  # e.g., "housing_rights", "legal_remedies", "procedures"


class ConceptGroupingService:
    """Service for grouping similar legal concepts using semantic similarity."""

    def __init__(self, similarity_threshold: float = 0.75, min_group_size: int = 2):
        self.similarity_threshold = similarity_threshold
        self.min_group_size = min_group_size
        self.logger = logging.getLogger(__name__)

        # Load spaCy model for semantic similarity
        self.nlp = spacy.load("en_core_web_lg")
        self.logger.info(
            f"Loaded spaCy model for concept grouping (threshold: {similarity_threshold})"
        )

    def group_similar_concepts(self, entities: List[LegalEntity]) -> List[ConceptGroup]:
        """
        Group entities by semantic similarity using spaCy embeddings.

        Args:
            entities: List of legal entities to group

        Returns:
            List of concept groups containing similar entities
        """
        self.logger.info(f"Grouping {len(entities)} entities by semantic similarity")

        if len(entities) < self.min_group_size:
            self.logger.info("Not enough entities to form groups")
            return []

        # Create spaCy documents for all entities
        entity_docs = {}
        for entity in entities:
            # Combine name and description for better semantic representation
            text = entity.name
            if entity.description:
                text += " " + entity.description

            entity_docs[entity.id] = self.nlp(text)

        # Find similar entities
        groups = self._find_similarity_groups(entities, entity_docs)

        # Convert to ConceptGroup objects
        concept_groups = []
        for group_id, group_entities in groups.items():
            if len(group_entities) >= self.min_group_size:
                group = self._create_concept_group(group_id, group_entities, entity_docs)
                concept_groups.append(group)

        self.logger.info(f"Created {len(concept_groups)} concept groups")
        return concept_groups

    def _find_similarity_groups(
        self, entities: List[LegalEntity], entity_docs: Dict[str, spacy.tokens.Doc]
    ) -> Dict[str, List[LegalEntity]]:
        """Find groups of similar entities using hierarchical clustering."""
        if len(entities) < self.min_group_size:
            return {}

        # Calculate similarity matrix
        similarity_matrix = self._build_similarity_matrix(entities, entity_docs)

        # Log some similarity examples for debugging
        if len(entities) > 1:
            self.logger.info(f"Sample similarities:")
            for i in range(min(3, len(entities))):
                for j in range(i + 1, min(4, len(entities))):
                    self.logger.info(
                        f"  '{entities[i].name}' vs '{entities[j].name}': {similarity_matrix[i][j]:.3f}"
                    )

        # Use hierarchical clustering to form groups
        groups = self._hierarchical_clustering(entities, similarity_matrix)

        # Filter groups by minimum size
        filtered_groups = {}
        for group_id, group_entities in groups.items():
            if len(group_entities) >= self.min_group_size:
                filtered_groups[group_id] = group_entities

        self.logger.info(f"Formed {len(filtered_groups)} groups from {len(entities)} entities")
        return filtered_groups

    def _build_similarity_matrix(
        self, entities: List[LegalEntity], entity_docs: Dict[str, spacy.tokens.Doc]
    ) -> List[List[float]]:
        """Build a similarity matrix between all entities."""
        n = len(entities)
        matrix = [[0.0 for _ in range(n)] for _ in range(n)]

        for i in range(n):
            for j in range(i + 1, n):
                similarity = self._calculate_similarity(
                    entity_docs[entities[i].id], entity_docs[entities[j].id]
                )
                matrix[i][j] = similarity
                matrix[j][i] = similarity  # Symmetric matrix

        return matrix

    def _hierarchical_clustering(
        self, entities: List[LegalEntity], similarity_matrix: List[List[float]]
    ) -> Dict[str, List[LegalEntity]]:
        """Perform hierarchical clustering to form groups."""
        n = len(entities)
        if n == 0:
            return {}

        # Initialize each entity as its own cluster
        clusters = [[i] for i in range(n)]

        # Continue merging clusters until no more merges are possible
        while len(clusters) > 1:
            best_merge = None
            best_similarity = -1

            # Find the best pair of clusters to merge
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    # Calculate average similarity between clusters
                    total_similarity = 0.0
                    count = 0

                    for idx1 in clusters[i]:
                        for idx2 in clusters[j]:
                            total_similarity += similarity_matrix[idx1][idx2]
                            count += 1

                    if count > 0:
                        avg_similarity = total_similarity / count
                        if (
                            avg_similarity > best_similarity
                            and avg_similarity >= self.similarity_threshold
                        ):
                            best_similarity = avg_similarity
                            best_merge = (i, j)

            # If no good merge found, stop
            if best_merge is None:
                break

            # Merge the best pair
            i, j = best_merge
            clusters[i].extend(clusters[j])

            # Remove the merged cluster
            clusters.pop(j)

            self.logger.debug(f"Merged clusters {i} and {j} with similarity {best_similarity:.3f}")

        # Convert clusters to groups
        groups = {}
        for i, cluster in enumerate(clusters):
            if len(cluster) >= self.min_group_size:
                group_id = f"group_{i}"
                groups[group_id] = [entities[idx] for idx in cluster]

        return groups

    def _calculate_similarity(self, doc1: spacy.tokens.Doc, doc2: spacy.tokens.Doc) -> float:
        """Calculate semantic similarity between two spaCy documents."""
        try:
            return doc1.similarity(doc2)
        except Exception as e:
            self.logger.warning(f"Error calculating similarity: {e}")
            return 0.0

    def _create_concept_group(
        self, group_id: str, entities: List[LegalEntity], entity_docs: Dict[str, spacy.tokens.Doc]
    ) -> ConceptGroup:
        """Create a ConceptGroup from a list of similar entities."""
        # Use the most representative entity name as group name
        group_name = self._get_representative_name(entities)

        # Create description from entity descriptions
        descriptions = [e.description for e in entities if e.description]
        group_description = " | ".join(descriptions[:3])  # Limit to first 3 descriptions

        # Calculate average similarity within the group
        total_similarity = 0.0
        similarity_count = 0

        for i, entity1 in enumerate(entities):
            for entity2 in entities[i + 1 :]:
                similarity = self._calculate_similarity(
                    entity_docs[entity1.id], entity_docs[entity2.id]
                )
                total_similarity += similarity
                similarity_count += 1

        avg_similarity = total_similarity / similarity_count if similarity_count > 0 else 0.0

        # Determine group type based on entity types
        group_type = self._determine_group_type(entities)

        return ConceptGroup(
            id=group_id,
            name=group_name,
            description=group_description,
            entities=entities,
            similarity_score=avg_similarity,
            group_type=group_type,
        )

    def _get_representative_name(self, entities: List[LegalEntity]) -> str:
        """Get the most representative name for a group of entities."""
        # Prefer shorter, more general names
        names = [e.name for e in entities]

        # Sort by length and prefer names without specific details
        names.sort(key=lambda x: (len(x), x.count(" ")))

        return names[0] if names else "Unknown Group"

    def _determine_group_type(self, entities: List[LegalEntity]) -> str:
        """Determine the type of concept group based on entity types."""
        type_counts = defaultdict(int)
        for entity in entities:
            type_counts[entity.entity_type] += 1

        # Return the most common entity type
        if type_counts:
            most_common_type = max(type_counts.items(), key=lambda x: x[1])[0]
            return most_common_type.lower()

        return "mixed"

    def find_similar_entities(
        self, query_entity: LegalEntity, candidate_entities: List[LegalEntity], top_k: int = 5
    ) -> List[Tuple[LegalEntity, float]]:
        """
        Find entities similar to a query entity.

        Args:
            query_entity: The entity to find similar entities for
            candidate_entities: List of entities to search through
            top_k: Maximum number of similar entities to return

        Returns:
            List of (entity, similarity_score) tuples, sorted by similarity
        """
        # Create query document
        query_text = query_entity.name
        if query_entity.description:
            query_text += " " + query_entity.description

        query_doc = self.nlp(query_text)

        # Calculate similarities
        similarities = []
        for candidate in candidate_entities:
            if candidate.id == query_entity.id:
                continue

            candidate_text = candidate.name
            if candidate.description:
                candidate_text += " " + candidate.description

            candidate_doc = self.nlp(candidate_text)

            similarity = self._calculate_similarity(query_doc, candidate_doc)
            similarities.append((candidate, similarity))

        # Sort by similarity and return top_k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]

    def suggest_relationships(
        self, entities: List[LegalEntity], existing_relationships: List[LegalRelationship]
    ) -> List[Tuple[LegalEntity, LegalEntity, float]]:
        """
        Suggest potential relationships between entities based on similarity.

        Args:
            entities: List of entities to analyze
            existing_relationships: List of existing relationships to avoid duplicates

        Returns:
            List of (source_entity, target_entity, similarity_score) tuples
        """
        suggestions = []
        existing_pairs = set()

        # Track existing relationships
        for rel in existing_relationships:
            existing_pairs.add((rel.source_id, rel.target_id))
            existing_pairs.add((rel.target_id, rel.source_id))

        # Find similar entity pairs
        for i, entity1 in enumerate(entities):
            for entity2 in entities[i + 1 :]:
                # Skip if relationship already exists
                if (entity1.id, entity2.id) in existing_pairs:
                    continue

                # Calculate similarity
                text1 = entity1.name + " " + (entity1.description or "")
                text2 = entity2.name + " " + (entity2.description or "")

                doc1 = self.nlp(text1)
                doc2 = self.nlp(text2)

                similarity = self._calculate_similarity(doc1, doc2)

                # Suggest relationship if similarity is high enough
                if similarity >= self.similarity_threshold:
                    suggestions.append((entity1, entity2, similarity))

        # Sort by similarity
        suggestions.sort(key=lambda x: x[2], reverse=True)
        return suggestions
