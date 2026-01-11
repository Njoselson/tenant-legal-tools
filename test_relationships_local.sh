#!/bin/bash

# Test script for relationships feature on local Docker Compose setup
# Usage: ./test_relationships_local.sh

set -e

API_URL="http://localhost:8000"
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "🔍 Testing Relationships Feature"
echo "API URL: $API_URL"
echo ""

# Check if API is running
echo "1. Checking if API is running..."
if curl -s -f "$API_URL/api/health" > /dev/null; then
    echo -e "   ${GREEN}✅ API is running${NC}"
else
    echo -e "   ${RED}❌ API is not running. Start it with: docker compose up${NC}"
    exit 1
fi
echo ""

# Test 1: Check current graph data
echo "2. Checking current graph data..."
GRAPH_DATA=$(curl -s "$API_URL/api/kg/graph-data?limit=50")
NODES_COUNT=$(echo "$GRAPH_DATA" | jq '.nodes | length')
LINKS_COUNT=$(echo "$GRAPH_DATA" | jq '.links | length')

echo "   Current nodes: $NODES_COUNT"
echo "   Current relationships (links): $LINKS_COUNT"

if [ "$LINKS_COUNT" -gt 0 ]; then
    echo -e "   ${GREEN}✅ Relationships exist in graph${NC}"
    echo ""
    echo "   Sample relationships:"
    echo "$GRAPH_DATA" | jq '.links[0:3] | .[] | "\(.source) -> \(.target): \(.label)"'
else
    echo -e "   ${YELLOW}⚠️  No relationships found yet${NC}"
    echo "   (This is OK if you haven't ingested documents yet)"
fi
echo ""

# Test 2: Check database directly
echo "3. Checking database directly (via Docker)..."
DB_RELS=$(docker compose exec -T app python -c "
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
kg = ArangoDBGraph()
rels = kg.get_relationships()
print(len(rels))
if rels:
    print(f'{rels[0].source_id} -> {rels[0].target_id}: {rels[0].relationship_type.name}')
" 2>/dev/null || echo "0")

DB_REL_COUNT=$(echo "$DB_RELS" | head -1)
echo "   Total relationships in database: $DB_REL_COUNT"

if [ "$DB_REL_COUNT" -gt 0 ]; then
    echo -e "   ${GREEN}✅ Relationships exist in database${NC}"
    if [ "$LINKS_COUNT" -eq 0 ]; then
        echo -e "   ${YELLOW}⚠️  Relationships in DB but not returned by API (this might be a bug)${NC}"
    fi
else
    echo -e "   ${YELLOW}⚠️  No relationships in database${NC}"
    echo "   Need to ingest a document to create relationships"
fi
echo ""

# Test 3: Ingest a test document
echo "4. Ingesting test document with relationships..."
INGEST_RESPONSE=$(curl -s -X POST "$API_URL/api/kg/process" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Warranty of Habitability (RPL §235-b) enables rent reduction remedy. The law requires evidence of code violations including photos and repair requests.",
    "source_type": "guide",
    "organization": "Test Organization",
    "document_type": "guide",
    "jurisdiction": "New York"
  }')

INGEST_STATUS=$(echo "$INGEST_RESPONSE" | jq -r '.status // "error"')
ADDED_ENTITIES=$(echo "$INGEST_RESPONSE" | jq '.added_entities // 0')
ADDED_RELS=$(echo "$INGEST_RESPONSE" | jq '.added_relationships // 0')

if [ "$INGEST_STATUS" = "success" ]; then
    echo -e "   ${GREEN}✅ Ingestion successful${NC}"
    echo "   Added entities: $ADDED_ENTITIES"
    echo "   Added relationships: $ADDED_RELS"
    
    if [ "$ADDED_RELS" -gt 0 ]; then
        echo -e "   ${GREEN}✅ Relationships were created during ingestion${NC}"
    else
        echo -e "   ${YELLOW}⚠️  No relationships created (this might be expected depending on extraction)${NC}"
    fi
else
    ERROR_MSG=$(echo "$INGEST_RESPONSE" | jq -r '.detail // .error // "Unknown error"')
    echo -e "   ${RED}❌ Ingestion failed: $ERROR_MSG${NC}"
fi
echo ""

# Wait a moment for processing
echo "5. Waiting 2 seconds for processing..."
sleep 2
echo ""

# Test 4: Check graph data after ingestion
echo "6. Checking graph data after ingestion..."
GRAPH_DATA_AFTER=$(curl -s "$API_URL/api/kg/graph-data?limit=50")
LINKS_COUNT_AFTER=$(echo "$GRAPH_DATA_AFTER" | jq '.links | length')

echo "   Relationships after ingestion: $LINKS_COUNT_AFTER"

if [ "$LINKS_COUNT_AFTER" -gt "$LINKS_COUNT" ]; then
    echo -e "   ${GREEN}✅ Relationship count increased after ingestion${NC}"
elif [ "$LINKS_COUNT_AFTER" -gt 0 ]; then
    echo -e "   ${GREEN}✅ Relationships are present${NC}"
else
    echo -e "   ${YELLOW}⚠️  Still no relationships (check logs for extraction errors)${NC}"
fi

if [ "$LINKS_COUNT_AFTER" -gt 0 ]; then
    echo ""
    echo "   Sample relationships:"
    echo "$GRAPH_DATA_AFTER" | jq '.links[0:5] | .[] | "   \(.source) --[\(.label)]--> \(.target)"'
fi
echo ""

# Test 5: Check specific relationship types
echo "7. Checking relationship types in database..."
REL_TYPES=$(docker compose exec -T app python -c "
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from collections import Counter

kg = ArangoDBGraph()
rels = kg.get_relationships()
types = Counter([r.relationship_type.name for r in rels])

print('Relationship types:')
for rt, count in sorted(types.items()):
    print(f'{rt}: {count}')
" 2>/dev/null || echo "No relationships")

echo "$REL_TYPES"
echo ""

# Test 6: Verify API endpoint structure
echo "8. Verifying API response structure..."
SAMPLE_LINK=$(echo "$GRAPH_DATA_AFTER" | jq '.links[0] // empty')

if [ -n "$SAMPLE_LINK" ] && [ "$SAMPLE_LINK" != "null" ]; then
    HAS_SOURCE=$(echo "$SAMPLE_LINK" | jq 'has("source")')
    HAS_TARGET=$(echo "$SAMPLE_LINK" | jq 'has("target")')
    HAS_LABEL=$(echo "$SAMPLE_LINK" | jq 'has("label")')
    
    if [ "$HAS_SOURCE" = "true" ] && [ "$HAS_TARGET" = "true" ] && [ "$HAS_LABEL" = "true" ]; then
        echo -e "   ${GREEN}✅ Link structure is correct (has source, target, label)${NC}"
    else
        echo -e "   ${RED}❌ Link structure is missing required fields${NC}"
        echo "   Sample link: $SAMPLE_LINK"
    fi
else
    echo -e "   ${YELLOW}⚠️  No links to verify structure${NC}"
fi
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$LINKS_COUNT_AFTER" -gt 0 ]; then
    echo -e "${GREEN}✅ Relationships feature appears to be working!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Open http://localhost:8000/kg-view in your browser"
    echo "2. You should see edges/lines connecting related entities"
    echo "3. Edge labels should show relationship types (e.g., ENABLES, REQUIRES)"
else
    echo -e "${YELLOW}⚠️  No relationships found${NC}"
    echo ""
    echo "Possible reasons:"
    echo "1. Document extraction didn't create relationships (check logs)"
    echo "2. Entities exist but relationships weren't extracted"
    echo "3. Need to ingest documents with explicit relationship statements"
    echo ""
    echo "Check logs: docker compose logs app | grep -i relationship"
fi

echo ""
echo "To view logs: docker compose logs -f app | grep -i relationship"
echo "To view kg-view: http://localhost:8000/kg-view"

