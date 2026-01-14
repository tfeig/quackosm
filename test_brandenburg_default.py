"""Test Brandenburg with default parameters to check if it's a pre-existing issue."""

from pathlib import Path
from quackosm import convert_pbf_to_parquet

if __name__ == "__main__":
    pbf_file = "brandenburg-latest.osm.pbf"

    if not Path(pbf_file).exists():
        print(f"ERROR: {pbf_file} not found!")
        exit(1)

    print("Testing Brandenburg with DEFAULT parameters (include_non_closed_relations=False)...")
    print("This will help determine if the crash is related to our changes or a pre-existing issue.")
    print("=" * 80)

    try:
        result = convert_pbf_to_parquet(
            pbf_file,
            include_non_closed_relations=False,  # Explicit default
            working_directory="files_brandenburg_default",
            verbosity_mode="verbose"  # Show all output
        )
        print(f"\n✓ Success: {result}")

    except Exception as e:
        print(f"\n✗ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
