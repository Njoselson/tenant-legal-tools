"""
Quote extraction service for highlighting entities in source text.
"""

import logging
import re
from typing import Dict, List

from tenant_legal_guidance.models.entities import LegalEntity
from tenant_legal_guidance.services.deepseek import DeepSeekClient


class QuoteExtractor:
    """Extract best quote for each entity during ingestion."""
    
    def __init__(self, llm_client: DeepSeekClient):
        self.llm_client = llm_client
        self.logger = logging.getLogger(__name__)
    
    async def extract_best_quote(
        self,
        entity: LegalEntity,
        chunks: List[Dict],
    ) -> Dict[str, str]:
        """
        Find best quote for entity.
        
        Args:
            entity: Legal entity to extract quote for
            chunks: List of chunks where entity was mentioned ({text, chunk_id, source_id})
            
        Returns: {
            "text": "Every landlord must maintain...",
            "source_id": "uuid-123",
            "chunk_id": "uuid-123:5",
            "explanation": "This quote defines the core obligation"
        }
        """
        # 1. Find all sentences mentioning entity.name across chunks
        candidates = []
        
        # Build flexible name variations for matching
        name_variations = self._build_name_variations(entity.name)
        
        for chunk in chunks:
            sentences = self._extract_sentences(chunk.get("text", ""))
            for sent in sentences:
                # Check if sentence mentions entity (exact match or variation)
                sent_lower = sent.lower()
                if (entity.name.lower() in sent_lower or 
                    any(var in sent_lower for var in name_variations)):
                    score = self._score_sentence(sent, entity, name_variations)
                    candidates.append({
                        "text": sent,
                        "score": score,
                        "chunk_id": chunk.get("chunk_id"),
                        "source_id": chunk.get("source_id")
                    })
        
        # If still no candidates, use a fallback strategy
        if not candidates:
            # Try to find any substantive sentence (definition or legal statement)
            for chunk in chunks:
                sentences = self._extract_sentences(chunk.get("text", ""))
                for sent in sentences:
                    # Score based on legal content, not name match
                    score = self._score_legal_sentence(sent)
                    if score > 0.3:  # Threshold for "good enough"
                        candidates.append({
                            "text": sent,
                            "score": score * 0.7,  # Penalize for no name match
                            "chunk_id": chunk.get("chunk_id"),
                            "source_id": chunk.get("source_id")
                        })
        
        if not candidates:
            # No quotes found
            return {
                "text": "",
                "source_id": chunks[0].get("source_id") if chunks else "",
                "chunk_id": chunks[0].get("chunk_id") if chunks else "",
                "explanation": f"No specific quote found for {entity.name}"
            }
        
        # 2. Pick highest-scoring sentence
        best = max(candidates, key=lambda x: x["score"])
        
        # 3. Generate explanation (LLM)
        explanation = await self._generate_explanation(entity, best["text"])
        
        return {
            "text": best["text"].strip(),
            "source_id": best["source_id"],
            "chunk_id": best["chunk_id"],
            "explanation": explanation
        }
    
    def _score_sentence(self, sentence: str, entity: LegalEntity, name_variations: List[str] = None) -> float:
        """
        Score sentence quality (0-1).
        
        Criteria:
        - Has definition markers? (+0.4)
        - Contains entity name + action verbs? (+0.3)
        - Grammatically complete? (+0.1)
        - Appropriate length (50-400 chars)? (+0.2)
        """
        score = 0.0
        sentence_lower = sentence.lower()
        
        # Has definition markers?
        definition_markers = ["means", "defined as", "refers to", "is when", "is", "are", "requires", "must", "shall"]
        if any(marker in sentence_lower for marker in definition_markers):
            score += 0.4
        
        # Contains entity name + action verbs?
        action_verbs = ["must", "shall", "requires", "prohibits", "allows", "enables", "permits", "mandates"]
        if any(verb in sentence_lower for verb in action_verbs):
            # Extra points if both entity name AND action verb present
            if entity.name.lower() in sentence_lower:
                score += 0.3
        
        # Grammatically complete?
        if sentence.strip().endswith(('.', '!', '?')):
            score += 0.1
        
        # Appropriate length (50-400 chars)?
        if 50 <= len(sentence) <= 400:
            score += 0.2
        
        return min(score, 1.0)
    
    def _build_name_variations(self, name: str) -> List[str]:
        """Build variations of entity name for flexible matching."""
        variations = [name.lower()]
        name_lower = name.lower()
        
        # Singular/plural variations
        if name_lower.endswith('s'):
            # Plural -> singular
            variations.append(name_lower[:-1])
        else:
            # Singular -> plural
            variations.append(name_lower + 's')
        
        # Remove common words that might not appear in quotes
        for word in ['the', 'of', 'in', 'a', 'an']:
            if word in name_lower:
                parts = name_lower.split(word)
                variations.extend([p.strip() for p in parts if p.strip()])
        
        # Add individual words from multi-word names
        words = name_lower.split()
        if len(words) > 1:
            variations.extend(words)
        
        return variations
    
    def _score_legal_sentence(self, sentence: str) -> float:
        """
        Score sentence based on legal content quality (without requiring name match).
        
        Useful for fallback when no name match is found.
        """
        score = 0.0
        sentence_lower = sentence.lower()
        
        # Has definition markers?
        definition_markers = ["means", "defined as", "refers to", "is when", "is", "are", "requires", "must", "shall"]
        if any(marker in sentence_lower for marker in definition_markers):
            score += 0.4
        
        # Contains legal action verbs?
        action_verbs = ["must", "shall", "requires", "prohibits", "allows", "enables", "permits", "mandates"]
        if any(verb in sentence_lower for verb in action_verbs):
            score += 0.3
        
        # Grammatically complete?
        if sentence.strip().endswith(('.', '!', '?')):
            score += 0.1
        
        # Appropriate length (50-400 chars)?
        if 50 <= len(sentence) <= 400:
            score += 0.2
        
        return min(score, 1.0)
    
    def _extract_sentences(self, text: str) -> List[str]:
        """
        Extract sentences from text.
        
        Simple sentence splitting on common sentence terminators.
        """
        # Split on sentence terminators
        sentences = re.split(r'[.!?]+', text)
        
        # Clean and filter empty sentences
        cleaned = [s.strip() for s in sentences if s.strip()]
        
        return cleaned
    
    async def _generate_explanation(
        self,
        entity: LegalEntity,
        quote_text: str
    ) -> str:
        """
        Generate explanation for why this quote is relevant.
        
        Uses LLM to generate 1-sentence explanation.
        """
        prompt = f"""Given this legal entity and quote, explain in 1 sentence why the quote is relevant.

Entity: {entity.name}
Type: {entity.entity_type.value}
Quote: "{quote_text}"

Provide a concise explanation (1 sentence):"""

        try:
            response = await self.llm_client.chat_completion(prompt)
            # Extract first sentence if LLM returns multiple
            explanation = response.split('.')[0].strip() + '.'
            return explanation
        except Exception as e:
            self.logger.error(f"Failed to generate explanation: {e}")
            return f"This quote demonstrates {entity.name}."
