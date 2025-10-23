#!/usr/bin/env python3
"""
CLI tool to reset or drop the ArangoDB database.

Usage:
  # Show current database stats
  python -m tenant_legal_guidance.scripts.reset_database --stats

  # Truncate all collections (keeps schema)
  python -m tenant_legal_guidance.scripts.reset_database --truncate

  # Drop entire database (complete removal)
  python -m tenant_legal_guidance.scripts.reset_database --drop

  # Dry-run mode (preview what will be deleted)
  python -m tenant_legal_guidance.scripts.reset_database --truncate --dry-run
"""

import argparse
import logging
import sys
from typing import Dict

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph


def print_stats(stats: Dict[str, int]):
    """Pretty print database statistics."""
    print("\n" + "=" * 60)
    print("DATABASE STATISTICS")
    print("=" * 60)

    if not stats:
        print("No collections found or error retrieving stats.")
        return

    total = 0
    for collection_name in sorted(stats.keys()):
        count = stats[collection_name]
        if count >= 0:
            print(f"  {collection_name:30} {count:>10,} documents")
            total += count
        else:
            print(f"  {collection_name:30} {'ERROR':>10}")

    print("-" * 60)
    print(f"  {'TOTAL':30} {total:>10,} documents")
    print("=" * 60 + "\n")


def confirm_action(action: str, dry_run: bool = False) -> bool:
    """Prompt user to confirm destructive action."""
    if dry_run:
        return True

    print(f"\n⚠️  WARNING: This will {action}!")
    print("This operation cannot be undone.")
    response = input("\nType 'yes' to confirm: ")
    return response.lower() == "yes"


def main():
    parser = argparse.ArgumentParser(
        description="Reset or drop the ArangoDB database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--stats", action="store_true", help="Show database statistics (collection counts)"
    )
    action_group.add_argument(
        "--truncate",
        action="store_true",
        help="Truncate all collections (keeps schema, removes data)",
    )
    action_group.add_argument(
        "--drop", action="store_true", help="Drop entire database (complete removal)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be deleted without actually deleting",
    )

    parser.add_argument(
        "--yes", action="store_true", help="Skip confirmation prompt (use with caution!)"
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    try:
        # Initialize connection
        print("Connecting to ArangoDB...")
        graph = ArangoDBGraph()
        print(f"Connected to database: {graph.db_name}\n")

        # Show stats
        if args.stats:
            stats = graph.get_database_stats()
            print_stats(stats)
            return 0

        # Get current stats for preview
        stats = graph.get_database_stats()

        # Truncate collections
        if args.truncate:
            print_stats(stats)

            if args.dry_run:
                print("DRY RUN: Would truncate all collections listed above.")
                print("No actual changes made.")
                return 0

            if not args.yes:
                if not confirm_action("DELETE ALL DATA from all collections"):
                    print("Aborted.")
                    return 1

            print("\nTruncating collections...")
            deleted_counts = graph.reset_database(confirm=True)

            print("\n" + "=" * 60)
            print("TRUNCATION COMPLETE")
            print("=" * 60)
            for collection_name in sorted(deleted_counts.keys()):
                count = deleted_counts[collection_name]
                if count >= 0:
                    print(f"  {collection_name:30} {count:>10,} documents deleted")
                else:
                    print(f"  {collection_name:30} {'ERROR':>10}")
            print("=" * 60 + "\n")

            return 0

        # Drop database
        if args.drop:
            print_stats(stats)

            if args.dry_run:
                print(f"DRY RUN: Would drop entire database '{graph.db_name}'.")
                print("No actual changes made.")
                return 0

            if not args.yes:
                if not confirm_action(f"PERMANENTLY DELETE database '{graph.db_name}'"):
                    print("Aborted.")
                    return 1

            print(f"\nDropping database '{graph.db_name}'...")
            success = graph.drop_database(confirm=True)

            if success:
                print(f"\n✓ Database '{graph.db_name}' dropped successfully.\n")
                return 0
            else:
                print(f"\n✗ Failed to drop database '{graph.db_name}'.\n")
                return 1

    except KeyboardInterrupt:
        print("\n\nAborted by user.")
        return 1
    except Exception as e:
        print(f"\n✗ Error: {e}\n")
        logging.exception("Error during database reset")
        return 1


if __name__ == "__main__":
    sys.exit(main())
