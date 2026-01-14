"""Quick test with Monaco to verify the feature works."""

from pathlib import Path
import geopandas as gpd
from quackosm import convert_pbf_to_parquet

pbf_file = "files/monaco-latest.osm.pbf"

print("Testing with Monaco PBF...")
print("=" * 80)

# Test with include_non_closed_relations=True
print("\nConverting with include_non_closed_relations=True...")
try:
    result = convert_pbf_to_parquet(
        pbf_file,
        include_non_closed_relations=True,
        working_directory="files_monaco_test"
    )
    print(f"✓ Success: {result}")

    # Analyze
    gdf = gpd.read_parquet(result)
    relations = gdf[gdf['feature_id'].str.startswith('relation/')]
    print(f"  Total features: {len(gdf)}")
    print(f"  Total relations: {len(relations)}")
    if len(relations) > 0:
        print(f"  Relation geometry types: {relations.geometry.type.value_counts().to_dict()}")

except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("Test complete!")
