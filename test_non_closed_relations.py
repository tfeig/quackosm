"""
Simple test script for non-closed relations feature.

Tests convert_pbf_to_parquet with brandenburg-latest.osm.pbf
"""

from pathlib import Path
import geopandas as gpd
from quackosm import convert_pbf_to_parquet

if __name__ == "__main__":
    # Path to the PBF file
    pbf_file = "brandenburg-latest.osm.pbf"

    if not Path(pbf_file).exists():
        print(f"ERROR: {pbf_file} not found!")
        print("Please download it first, e.g.:")
        print("  wget https://download.geofabrik.de/europe/germany/brandenburg-latest.osm.pbf")
        exit(1)

    print("=" * 80)
    print("Testing non-closed relations feature")
    print("=" * 80)

    # Test 1: Default behavior (exclude non-closed relations)
    print("\n[1/2] Converting with include_non_closed_relations=False (default)...")
    result_default = convert_pbf_to_parquet(
        pbf_file,
        include_non_closed_relations=False,
        working_directory="files_test_default"
    )
    print(f"✓ Result file: {result_default}")

    # Read and analyze
    gdf_default = gpd.read_parquet(result_default)
    relations_default = gdf_default[gdf_default['feature_id'].str.startswith('relation/')]
    print(f"  Total features: {len(gdf_default)}")
    print(f"  Total relations: {len(relations_default)}")
    if len(relations_default) > 0:
        print(f"  Relation geometry types: {relations_default.geometry.type.value_counts().to_dict()}")

    # Test 2: Include non-closed relations
    print("\n[2/2] Converting with include_non_closed_relations=True...")
    result_enabled = convert_pbf_to_parquet(
        pbf_file,
        include_non_closed_relations=True,
        working_directory="files_test_enabled"
    )
    print(f"✓ Result file: {result_enabled}")

    # Read and analyze
    gdf_enabled = gpd.read_parquet(result_enabled)
    relations_enabled = gdf_enabled[gdf_enabled['feature_id'].str.startswith('relation/')]
    print(f"  Total features: {len(gdf_enabled)}")
    print(f"  Total relations: {len(relations_enabled)}")
    if len(relations_enabled) > 0:
        print(f"  Relation geometry types: {relations_enabled.geometry.type.value_counts().to_dict()}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Relations with include_non_closed_relations=False: {len(relations_default)}")
    print(f"Relations with include_non_closed_relations=True:  {len(relations_enabled)}")
    print(f"Difference (additional relations):                 {len(relations_enabled) - len(relations_default)}")

    if len(relations_enabled) > len(relations_default):
        print("\n✓ SUCCESS: Non-closed relations are now included!")

        # Show examples of non-closed relations (MultiLineString or GeometryCollection)
        non_polygon_relations = relations_enabled[
            ~relations_enabled.geometry.type.isin(['Polygon', 'MultiPolygon'])
        ]

        if len(non_polygon_relations) > 0:
            print(f"\nFound {len(non_polygon_relations)} non-polygon relations:")
            print(non_polygon_relations[['feature_id', 'geometry']].head(10))
    else:
        print("\n⚠ WARNING: No difference found. Brandenburg might not have non-closed relations,")
        print("           or they might be filtered out by default tag filtering.")

    print("\n" + "=" * 80)
    print("Test complete!")
    print("=" * 80)
