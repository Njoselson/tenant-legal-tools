# Testing Entity Relationships in KG View

## Overview

After deploying the fixes, you need to verify that:
1. Relationships are being created during document ingestion
2. Relationships are visible in the knowledge graph view
3. Relationships are correctly displayed between entities

## Test Steps

### 1. Verify Relationships Are Created During Ingestion

#### Test via API (Ingest a Document)

```bash
# From your local machine or server
curl -X POST http://YOUR_SERVER_IP/api/kg/process \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Warranty of Habitability enables rent reduction remedy. The law requires evidence of code violations.",
    "source_type": "guide",
    "organization": "Test Org",
    "document_type": "guide"
  }'
```

**Expected Response:**
- Status: 200 OK
- Should include `added_relationships` count > 0
- Check logs: `docker compose logs app | grep -i "relationship"`

#### Check Relationships in Database

```bash
# SSH into server
ssh root@YOUR_SERVER_IP
cd /opt/tenant_legal_guidance

# Check if relationships exist in ArangoDB
docker compose exec app python -c "
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
kg = ArangoDBGraph()
rels = kg.get_relationships()
print(f'Total relationships: {len(rels)}')
for rel in rels[:5]:
    print(f'{rel.source_id} -> {rel.target_id}: {rel.relationship_type.name}')
"
```

**Expected:**
- Should show relationships with relationship types (e.g., ENABLES, REQUIRES)

### 2. Verify Relationships Are Visible in KG View

#### Access KG View in Browser

1. Open your browser and go to: `http://YOUR_SERVER_IP/kg-view` or `https://YOUR_DOMAIN/kg-view`

2. **Visual Check:**
   - Entities should appear as nodes
   - **Relationships should appear as edges/lines connecting nodes**
   - Edges should have labels showing relationship types (e.g., "ENABLES", "REQUIRES")

#### Check API Endpoint Directly

```bash
# Get graph data (includes relationships)
curl http://YOUR_SERVER_IP/api/kg/graph-data?limit=50 | jq '.links | length'

# Should return a number > 0 if relationships exist
```

**Expected Response:**
```json
{
  "nodes": [...],
  "links": [
    {
      "source": "entity_id_1",
      "target": "entity_id_2",
      "label": "ENABLES",
      "weight": 1.0,
      "conditions": null
    }
  ],
  "next_cursor": null
}
```

### 3. Verify Specific Relationship Types

#### Check for Proof Chain Relationships

```bash
# Check for proof chain relationships (from case documents)
docker compose exec app python -c "
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.relationships import RelationshipType

kg = ArangoDBGraph()
rels = kg.get_relationships()

# Count by type
types = {}
for rel in rels:
    rt = rel.relationship_type.name
    types[rt] = types.get(rt, 0) + 1

print('Relationship types and counts:')
for rt, count in sorted(types.items()):
    print(f'  {rt}: {count}')
"
```

**Expected:**
- Should show various relationship types: ENABLES, REQUIRES, SUPPORTS, APPLIES_TO, etc.

### 4. Test Relationship Display in UI

#### Visual Inspection Checklist

- [ ] Load kg-view page
- [ ] See entity nodes displayed
- [ ] See edges/lines connecting related entities
- [ ] Edge labels show relationship types (e.g., "ENABLES", "REQUIRES")
- [ ] Click on an entity shows its relationships in the details panel
- [ ] Both incoming and outgoing relationships are visible

#### Test Edge Cases

1. **Entities with no relationships:**
   - Should display as isolated nodes (no edges)
   - Should still be visible

2. **Entities with many relationships:**
   - Should show all relationships (based on current pagination)
   - Graph should be readable (not too cluttered)

3. **Different relationship types:**
   - Should be distinguishable (via labels, colors, or styling)
   - Labels should be clear and readable

### 5. Browser Console Check

Open browser developer console (F12) and check:

```javascript
// In browser console on kg-view page
// Check if relationships are loaded
fetch('/api/kg/graph-data?limit=50')
  .then(r => r.json())
  .then(data => {
    console.log('Nodes:', data.nodes.length);
    console.log('Links (relationships):', data.links.length);
    console.log('Sample links:', data.links.slice(0, 5));
  });
```

**Expected:**
- `links.length` should be > 0
- Links should have `source`, `target`, and `label` properties

### 6. End-to-End Test: Ingest and View

```bash
# 1. Ingest a test document with known relationships
curl -X POST http://YOUR_SERVER_IP/api/kg/process \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Warranty of Habitability (RPL §235-b) enables rent reduction remedy. Evidence required includes photos of violations and repair requests.",
    "source_type": "statute",
    "organization": "NYC",
    "document_type": "statute",
    "jurisdiction": "New York City"
  }'

# 2. Wait a few seconds for processing

# 3. Check graph data
curl http://YOUR_SERVER_IP/api/kg/graph-data?limit=100 | jq '{
  nodes: (.nodes | length),
  links: (.links | length),
  sample_links: .links[0:3]
}'

# 4. Open browser to kg-view and verify relationships are visible
```

### 7. Check Logs for Relationship Creation

```bash
# SSH into server
ssh root@YOUR_SERVER_IP
cd /opt/tenant_legal_guidance

# Watch logs during ingestion
docker compose logs -f app | grep -i "relationship\|edge\|link"

# Or check recent logs
docker compose logs --tail=200 app | grep -i "relationship"
```

**Expected log messages:**
- "Added relationship: ..."
- "Stored relationship ..."
- Relationship counts in ingestion results

### 8. Verify Entity Details Show Relationships

```bash
# Get an entity ID first
ENTITY_ID=$(curl -s http://YOUR_SERVER_IP/api/kg/graph-data?limit=10 | jq -r '.nodes[0].id')

# Check relationships for that entity
curl http://YOUR_SERVER_IP/api/kg/expand \
  -H "Content-Type: application/json" \
  -d "{\"node_ids\": [\"$ENTITY_ID\"], \"per_node_limit\": 10}" | jq '.links'
```

**Expected:**
- Should return relationships connected to that entity
- Both incoming (`target_id` matches entity) and outgoing (`source_id` matches entity)

## Troubleshooting

### If relationships aren't showing:

1. **Check if relationships exist in database:**
   ```bash
   docker compose exec app python -c "
   from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
   kg = ArangoDBGraph()
   rels = kg.get_relationships()
   print(f'Relationships in DB: {len(rels)}')
   "
   ```

2. **Check API response:**
   ```bash
   curl http://YOUR_SERVER_IP/api/kg/graph-data?limit=50 | jq '.links'
   ```

3. **Check browser console for errors:**
   - Open kg-view page
   - Open DevTools (F12)
   - Check Console tab for JavaScript errors
   - Check Network tab to see if `/api/kg/graph-data` returns links

4. **Verify frontend code:**
   ```bash
   # Check if frontend is processing links correctly
   # Look at kg_view.html to ensure it processes the 'links' array
   ```

### If relationships exist but aren't visible:

1. Check graph visualization library is rendering edges
2. Check CSS/styling isn't hiding edges
3. Verify `links` array is being passed to visualization library
4. Check browser console for rendering errors

## Success Criteria

✅ **Relationships are created during ingestion**
- `added_relationships` > 0 in ingestion response
- Relationships visible in database query

✅ **Relationships are returned by API**
- `/api/kg/graph-data` returns `links` array with length > 0
- Links have correct structure (source, target, label)

✅ **Relationships are visible in UI**
- Edges appear between related entities
- Edge labels show relationship types
- Entity details panel shows connected relationships

✅ **Relationship types are correct**
- Relationship types match expected types (ENABLES, REQUIRES, etc.)
- Relationships make semantic sense

## Quick Test Script

Save this as `test_relationships.sh`:

```bash
#!/bin/bash

SERVER=${1:-"http://localhost:8000"}

echo "Testing relationships feature..."
echo "Server: $SERVER"
echo ""

# Test 1: Check graph data endpoint
echo "1. Checking graph data endpoint..."
LINKS=$(curl -s "$SERVER/api/kg/graph-data?limit=50" | jq '.links | length')
echo "   Found $LINKS relationships"
if [ "$LINKS" -gt 0 ]; then
    echo "   ✅ Relationships exist"
else
    echo "   ⚠️  No relationships found"
fi
echo ""

# Test 2: Get sample relationship
echo "2. Sample relationships:"
curl -s "$SERVER/api/kg/graph-data?limit=50" | jq '.links[0:3]'
echo ""

# Test 3: Check entity with relationships
echo "3. Checking entities with relationships..."
curl -s "$SERVER/api/kg/graph-data?limit=10" | jq '{
  total_nodes: (.nodes | length),
  total_links: (.links | length),
  nodes_with_relationships: ([.nodes[].id] | unique | length)
}'
echo ""

echo "Done! Open $SERVER/kg-view in browser to visually verify relationships."
```

Run it:
```bash
chmod +x test_relationships.sh
./test_relationships.sh http://YOUR_SERVER_IP
```

