"""Debug test to see where the error occurs."""

from pathlib import Path
from quackosm import convert_pbf_to_parquet

pbf_file = "/mnt/c/develop/projects/geoservices/pois/brandenburg-latest.osm.pbf"

if not Path(pbf_file).exists():
    print(f"ERROR: {pbf_file} not found!")
    exit(1)

print("Testing with default behavior and debug enabled...")

try:
    result = convert_pbf_to_parquet(
        pbf_file,
        include_non_closed_relations=False,
        working_directory="files_test_debug",
        debug_memory=True,  # Keep temp files
        debug_times=True,   # Show timing
    )
    print(f"✓ Success: {result}")
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
