#!/usr/bin/env python3
"""Validate a manifest JSONL file format."""

import json
import sys
from pathlib import Path

from tenant_legal_guidance.models.metadata_schemas import ManifestEntry


def validate_manifest_file(manifest_path: Path) -> tuple[int, int]:
    """Validate a manifest file and return (valid, invalid) counts."""
    valid_count = 0
    invalid_count = 0
    
    print(f"Validating manifest: {manifest_path}\n")
    
    with manifest_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
                entry = ManifestEntry(**data)
                valid_count += 1
                
                # Show first few valid entries
                if valid_count <= 3:
                    print(f"✓ Line {line_num}: Valid entry")
                    print(f"  Locator: {entry.locator[:80]}...")
                    print(f"  Title: {entry.title or '(no title)'}")
                    print()
                
            except json.JSONDecodeError as e:
                invalid_count += 1
                print(f"✗ Line {line_num}: Invalid JSON")
                print(f"  Error: {e}")
                print(f"  Content: {line[:100]}...")
                print()
            except Exception as e:
                invalid_count += 1
                print(f"✗ Line {line_num}: Invalid manifest entry")
                print(f"  Error: {e}")
                print(f"  Content: {line[:100]}...")
                print()
    
    return valid_count, invalid_count


def show_example_entry():
    """Show an example of a valid manifest entry."""
    print("\n" + "=" * 60)
    print("EXAMPLE VALID MANIFEST ENTRY")
    print("=" * 60)
    print()
    
    example = {
        "locator": "https://law.justia.com/cases/new-york/other-courts/2025/case.html",
        "kind": "URL",
        "title": "756 Liberty Realty LLC v Garcia",
        "jurisdiction": "New York State",
        "authority": "binding_legal_authority",
        "document_type": "court_opinion",
        "organization": None,
        "tags": ["housing_court", "habitability"],
        "notes": None
    }
    
    print(json.dumps(example, indent=2))
    print()
    
    print("REQUIRED FIELDS:")
    print("  - locator: URL or file path (required)")
    print()
    
    print("OPTIONAL FIELDS:")
    print("  - kind: 'URL', 'FILE', etc. (default: 'URL')")
    print("  - title: Document title")
    print("  - jurisdiction: Legal jurisdiction (e.g., 'NYC', 'New York State')")
    print("  - authority: Source authority level")
    print("    * 'binding_legal_authority' - Statutes, case law")
    print("    * 'practical_self_help' - Tenant guides")
    print("    * 'informational_only' - General info")
    print("  - document_type: Type of document")
    print("    * 'court_opinion' - Court decisions")
    print("    * 'statute' - Laws, codes")
    print("    * 'self_help_guide' - Tenant guides")
    print("  - organization: Publishing organization")
    print("  - tags: Array of strings (e.g., ['housing_court', 'repairs'])")
    print("  - notes: Additional notes")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_manifest.py <manifest.jsonl>")
        print("\nValidates a manifest JSONL file format.")
        show_example_entry()
        sys.exit(1)
    
    manifest_path = Path(sys.argv[1])
    
    if not manifest_path.exists():
        print(f"Error: File not found: {manifest_path}")
        sys.exit(1)
    
    valid, invalid = validate_manifest_file(manifest_path)
    
    print("=" * 60)
    print(f"VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Valid entries:   {valid}")
    print(f"Invalid entries: {invalid}")
    print(f"Total:           {valid + invalid}")
    print()
    
    if invalid == 0:
        print("✓ All entries are valid!")
        sys.exit(0)
    else:
        print(f"✗ Found {invalid} invalid entries. Please fix them.")
        sys.exit(1)

