"""
Convert OSM PBF file to GeoParquet including all relation types.

This script converts an OSM PBF file to GeoParquet format with
include_non_closed_relations=True, which includes all relation types
(site, route, network, etc.) and allows non-closed geometries.

Known Limitation: Only direct way members of relations are processed.
Relations with sub-relation members (e.g., type=site with nested
multipolygon buildings) will have incomplete geometries - only the
direct way members are extracted.

Usage:
    python convert_with_all_relations.py <pbf_file> [output_dir]

Examples:
    python convert_with_all_relations.py brandenburg-latest.osm.pbf
    python convert_with_all_relations.py data/city.osm.pbf output/
"""

import sys
from pathlib import Path
from quackosm import convert_pbf_to_parquet


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("ERROR: PBF file path required")
        print()
        print("Usage:")
        print("  python convert_with_all_relations.py <pbf_file> [output_dir]")
        print()
        print("Examples:")
        print("  python convert_with_all_relations.py brandenburg-latest.osm.pbf")
        print("  python convert_with_all_relations.py data/city.osm.pbf output/")
        sys.exit(1)

    pbf_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "files_all_relations"

    if not Path(pbf_file).exists():
        print(f"ERROR: File not found: {pbf_file}")
        sys.exit(1)

    print("=" * 80)
    print(f"Converting: {pbf_file}")
    print(f"Output directory: {output_dir}")
    print(f"Mode: include_non_closed_relations=True")
    print("=" * 80)
    print()

    try:
        result = convert_pbf_to_parquet(
            pbf_file,
            include_non_closed_relations=True,
            working_directory=output_dir,
            verbosity_mode="verbose"
        )

        print()
        print("=" * 80)
        print(f"✓ SUCCESS: {result}")
        print("=" * 80)

    except Exception as e:
        print()
        print("=" * 80)
        print(f"✗ ERROR: {type(e).__name__}: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        sys.exit(1)
