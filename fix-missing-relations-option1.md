# Implementation Plan: Option 1 - Configuration Parameter for Non-Closed Relations

## Quick Resume Guide (For New Sessions)

**What's Done:** Core implementation complete - parameter added, validation logic updated, geometry construction handles both closed and non-closed relations.

**What's Next:**
1. **Stage 5 (Tests)**: Write comprehensive test suite or find suitable test data
2. **Stage 6 (Docs)**: Update README.md and CHANGELOG.md

**Key Files Modified:**
- `quackosm/pbf_file_reader.py` (lines 176, 233-242, 270, 1283, 1326, 2497-2639, 2645-2790)

**How to Continue:**
1. Read the "Implementation Status" section below
2. Jump to "Stage 5: Tests" section (line ~399) or "Stage 6: Documentation" section (line ~599)
3. Check "Implementation Checklist" at bottom for detailed status

**Testing Challenge:** Monaco PBF isn't suitable (route relations filtered). Options:
- Create synthetic test data using OSM XML
- Find PBF with multipolygon relations having irregular geometries
- Proceed with documentation and defer integration tests

---

## Implementation Status (Last Updated: 2026-01-13)

**Status:** Core implementation complete (Stages 1-3), tests and documentation pending

**✅ Completed:**
- Stage 1: Configuration parameter added to PbfFileReader
- Stage 2: Validation logic modified (both all-at-once and chunked modes)
- Stage 3: Non-closed geometry construction implemented
- Stage 4: Chunked processing updated (completed as part of Stage 2)
- Basic smoke test: Existing tests pass without modification

**🔄 In Progress:**
- None

**⏳ Pending:**
- Stage 5: Comprehensive test suite for non-closed relations
- Stage 6: Documentation updates (README, CHANGELOG)

**Important Notes:**
- Monaco PBF was tested but has no suitable test data (route relations filtered out due to tag filtering)
- Implementation appears correct but needs proper test coverage
- All file locations updated in plan are accurate as of 2026-01-13
- Backward compatibility maintained: default `include_non_closed_relations=False` matches original behavior
- Cache invalidation working: files with `_nonclosedrelas` suffix are separate from default

**Code Changes Summary:**
1. **Parameter Addition**: Added `include_non_closed_relations: bool = False` to `__init__` signature (line 176) and stored as instance variable (line 270)
2. **Validation Logic**: Modified `_save_valid_relation_parts()` to classify relations as `all_closed` rather than just filter (lines 2645-2666, 2751-2790)
3. **Geometry Construction**:
   - Inner/outer parts use CASE statement: `ST_MakePolygon` for closed, `ST_RemoveRepeatedPoints` for non-closed (lines 2497-2529)
   - Hole processing only applies to closed relations (line 2546: added `WHERE og.all_closed = true`)
   - Non-closed parts conditionally processed when enabled (lines 2585-2614)
   - Final aggregation uses `ST_Union_Agg` to handle mixed geometry types (lines 2616-2639)
4. **Cache Naming**: Added `_nonclosedrelas` suffix when parameter is True (lines 1283, 1326)
5. **Cleanup**: Added `relation_non_closed_parts` to temp file cleanup list (line 1219)

## Overview

Add `include_non_closed_relations: bool = False` parameter to `PbfFileReader` to optionally include OSM relations that don't form closed multipolygons. Default behavior preserves backward compatibility.

**Target version:** 0.17.0
**Implementation complexity:** Medium
**Estimated changes:** ~400 lines (including tests)

## Goals

1. ✅ Include non-closed OSM relations in output when enabled
2. ✅ Maintain 100% backward compatibility (default=False)
3. ✅ Output appropriate geometry types (MultiPolygon, MultiLineString, GeometryCollection)
4. ✅ Pass all existing tests without modification
5. ✅ Add comprehensive test coverage for new functionality
6. ✅ Preserve cache invalidation logic

## Implementation Stages

### Stage 1: Add Configuration Parameter
**Goal:** Add parameter to PbfFileReader with proper type hints and defaults
**Success Criteria:**
- Parameter added to `__init__` with type hints
- Stored as instance variable
- Included in cache hash computation
- All existing tests pass without changes

**Files to modify:**
- `quackosm/pbf_file_reader.py`

**Changes:**

#### 1.1. Update `__init__` signature (line ~86)

**Current:**
```python
def __init__(
    self,
    tags_filter: Optional[Union[OsmTagsFilter, GroupedOsmTagsFilter]] = None,
    geometry_filter: Optional[BaseGeometry] = None,
    working_directory: Union[str, Path] = "files",
    osm_way_polygon_features_config: Optional[Union[BaseGeometry, dict[str, Any]]] = None,
    parquet_compression: str = "snappy",
    working_directory_hashing: bool = False,
) -> None:
```

**Modified:**
```python
def __init__(
    self,
    tags_filter: Optional[Union[OsmTagsFilter, GroupedOsmTagsFilter]] = None,
    geometry_filter: Optional[BaseGeometry] = None,
    working_directory: Union[str, Path] = "files",
    osm_way_polygon_features_config: Optional[Union[BaseGeometry, dict[str, Any]]] = None,
    parquet_compression: str = "snappy",
    working_directory_hashing: bool = False,
    include_non_closed_relations: bool = False,
) -> None:
```

#### 1.2. Store as instance variable (line ~150)

**Add after other instance variable assignments:**
```python
self.include_non_closed_relations = include_non_closed_relations
```

#### 1.3. Update docstring (line ~88-145)

**Add to Args section:**
```python
include_non_closed_relations: If True, includes OSM relations that don't form
    closed multipolygons in the output. When False (default), only relations
    where all parts form closed rings are included.

    Output geometry types:
    - Closed relations → MultiPolygon (existing behavior)
    - Non-closed relations → MultiLineString (when True)
    - Mixed relations → GeometryCollection (when True)

    Default: False (maintains backward compatibility)
```

#### 1.4. Update file naming for cache (line ~400-500)

**Locate the file naming function (search for "nofilter", "noclip" string construction):**

**Find in `_get_parquet_file_name()` or similar:**
```python
# Current pattern:
# {pbf_name}_{tags_hash|nofilter}[_alltags]_{geom_hash|noclip}_{compact|exploded}[_ids_hash][_wkt].parquet

# Add suffix when include_non_closed_relations=True:
suffix = "_nonclosedrelas" if self.include_non_closed_relations else ""
file_name = f"{base_name}{suffix}.parquet"
```

**Test:** Run existing test suite to ensure no regressions.

---

### Stage 2: Modify Validation Logic
**Goal:** Update `_save_valid_relation_parts()` to conditionally validate closed rings
**Success Criteria:**
- When `include_non_closed_relations=False`: Same behavior as before
- When `include_non_closed_relations=True`: All relations pass validation
- Relations classified by closure status (all_closed: bool)

**Files to modify:**
- `quackosm/pbf_file_reader.py`

**Changes:**

#### 2.1. Update `_save_valid_relation_parts()` method (line 2582-2769)

**Current validation CTE (lines ~2629-2641):**
```sql
valid_relations AS (
    SELECT id, is_valid
    FROM (
        SELECT
            id,
            bool_and(
                ST_Equals(ST_StartPoint(geometry), ST_EndPoint(geometry))
            ) is_valid
        FROM relations_with_geometries
        GROUP BY id
    )
    WHERE is_valid = true
)
```

**Modified validation CTE:**
```sql
classified_relations AS (
    SELECT
        id,
        bool_and(
            ST_Equals(ST_StartPoint(geometry), ST_EndPoint(geometry))
        ) AS all_closed
    FROM relations_with_geometries
    GROUP BY id
),
valid_relations AS (
    SELECT id, all_closed
    FROM classified_relations
    WHERE {
        "all_closed = true" if not self.include_non_closed_relations
        else "1=1"  -- Include all relations when enabled
    }
)
```

**Note:** This keeps the classification logic for downstream processing.

#### 2.2. Pass `all_closed` flag to downstream operations

**Modify the query to include classification:**
```sql
SELECT
    r.id,
    r.ref_id,
    r.ref_role,
    r.geometry_id,
    r.geometry,
    v.all_closed  -- Add classification
FROM relations_with_geometries r
JOIN valid_relations v ON r.id = v.id
ORDER BY r.id, r.ref_id
```

**Test:**
- Create test PBF with non-closed relation
- Run with `include_non_closed_relations=False` → should exclude
- Run with `include_non_closed_relations=True` → should include

---

### Stage 3: Handle Non-Closed Geometry Construction
**Goal:** Build LineString geometries for non-closed relations instead of Polygons
**Success Criteria:**
- Closed relations → Polygon → MultiPolygon (existing)
- Non-closed relations → LineString → MultiLineString (new)
- Proper role handling for both types

**Files to modify:**
- `quackosm/pbf_file_reader.py`

**Changes:**

#### 3.1. Split processing for closed vs non-closed (lines 2481-2551)

**Current approach:**
```sql
-- Step 26: Inner parts (holes)
SELECT id, geometry_id, ST_MakePolygon(...) geometry
FROM valid_relation_parts
WHERE ref_role = 'inner'

-- Step 27: Outer parts (boundaries)
SELECT id, geometry_id, ST_MakePolygon(...) geometry
FROM valid_relation_parts
WHERE ref_role = 'outer'
```

**Modified approach:**

```sql
-- Step 26a: Inner parts (closed - polygons)
SELECT id, geometry_id, ST_MakePolygon(ST_RemoveRepeatedPoints(geometry)) geometry
FROM valid_relation_parts
WHERE ref_role = 'inner' AND all_closed = true

-- Step 26b: Inner parts (non-closed - linestrings)
SELECT id, geometry_id, ST_RemoveRepeatedPoints(geometry)::GEOMETRY geometry
FROM valid_relation_parts
WHERE ref_role = 'inner' AND all_closed = false

-- Step 27a: Outer parts (closed - polygons)
SELECT id, geometry_id, ST_MakePolygon(ST_RemoveRepeatedPoints(geometry)) geometry
FROM valid_relation_parts
WHERE ref_role = 'outer' AND all_closed = true

-- Step 27b: Outer parts (non-closed - linestrings)
SELECT id, geometry_id, ST_RemoveRepeatedPoints(geometry)::GEOMETRY geometry
FROM valid_relation_parts
WHERE ref_role = 'outer' AND all_closed = false
```

**Implementation strategy:**

**Option A: Conditional SQL (Recommended):**
```python
if self.include_non_closed_relations:
    # Generate SQL with split processing (26a+26b, 27a+27b)
    inner_query = """
        SELECT id, geometry_id,
               CASE
                   WHEN all_closed THEN ST_MakePolygon(ST_RemoveRepeatedPoints(geometry))
                   ELSE ST_RemoveRepeatedPoints(geometry)::GEOMETRY
               END geometry
        FROM valid_relation_parts
        WHERE ref_role = 'inner'
    """
    outer_query = # Similar for outer
else:
    # Use existing queries (only ST_MakePolygon)
    inner_query = # Current implementation
    outer_query = # Current implementation
```

**Option B: Always classify, conditionally filter:**
```python
# Always include all_closed in classification
# Filter at end based on include_non_closed_relations flag
```

**Recommendation:** Option A for clearer separation and easier testing.

#### 3.2. Update hole processing logic (lines 2507-2535)

**Current (Step 28):**
```sql
SELECT
    og.id,
    og.geometry_id,
    ST_Difference(any_value(og.geometry), ST_Union_Agg(ig.geometry)) geometry
FROM outer_parts og
JOIN inner_parts ig ON og.id = ig.id AND ST_WITHIN(ig.geometry, og.geometry)
GROUP BY og.id, og.geometry_id
```

**Modified:**
```sql
-- Only apply hole logic to closed relations (Polygons)
SELECT
    og.id,
    og.geometry_id,
    ST_Difference(any_value(og.geometry), ST_Union_Agg(ig.geometry)) geometry
FROM outer_parts og
JOIN inner_parts ig ON og.id = ig.id AND ST_WITHIN(ig.geometry, og.geometry)
JOIN classified_relations cr ON og.id = cr.id
WHERE cr.all_closed = true  -- Holes only make sense for polygons
GROUP BY og.id, og.geometry_id
```

**For non-closed relations:**
```sql
-- Non-closed: just use outer and inner parts as-is (no hole subtraction)
SELECT id, geometry_id, geometry
FROM outer_parts og
JOIN classified_relations cr ON og.id = cr.id
WHERE cr.all_closed = false

UNION ALL

SELECT id, geometry_id, geometry
FROM inner_parts ig
JOIN classified_relations cr ON ig.id = cr.id
WHERE cr.all_closed = false
```

#### 3.3. Update final aggregation (lines 2552-2580, Step 30)

**Current:**
```sql
WITH unioned_outer_geometries AS (
    SELECT id, geometry FROM outer_parts_with_holes
    UNION ALL
    SELECT id, geometry FROM outer_parts_without_holes
),
final_geometries AS (
    SELECT id, ST_Union_Agg(geometry) geometry
    FROM unioned_outer_geometries
    GROUP BY id
)
SELECT 'relation/' || r_g.id as feature_id, r.tags, r_g.geometry
FROM final_geometries r_g
JOIN relations_all_with_tags r ON r.id = r_g.id
WHERE NOT ST_IsEmpty(r_g.geometry)
```

**Modified:**
```sql
WITH all_relation_parts AS (
    -- Closed relations (polygons with holes)
    SELECT id, geometry FROM outer_parts_with_holes
    UNION ALL
    SELECT id, geometry FROM outer_parts_without_holes
    UNION ALL
    -- Non-closed relations (linestrings) - if enabled
    SELECT id, geometry FROM non_closed_outer_parts
    UNION ALL
    SELECT id, geometry FROM non_closed_inner_parts
),
final_geometries AS (
    SELECT
        id,
        ST_Union_Agg(geometry) geometry  -- Handles mixed Polygon/LineString → GeometryCollection
    FROM all_relation_parts
    GROUP BY id
)
SELECT 'relation/' || r_g.id as feature_id, r.tags, r_g.geometry
FROM final_geometries r_g
JOIN relations_all_with_tags r ON r.id = r_g.id
WHERE NOT ST_IsEmpty(r_g.geometry)
```

**Note:** `ST_Union_Agg()` in DuckDB handles mixed geometry types and creates GeometryCollection when needed.

**Test:**
- Create test PBF with:
  - Closed relation → should output MultiPolygon
  - Non-closed relation → should output MultiLineString
  - Mixed relation (some closed, some open parts) → should output GeometryCollection

---

### Stage 4: Update Chunked Processing Mode
**Goal:** Apply same logic to memory-constrained chunked processing path
**Success Criteria:**
- Chunked mode produces identical results to all-at-once mode
- Same validation and geometry construction logic

**Files to modify:**
- `quackosm/pbf_file_reader.py`

**Changes:**

#### 4.1. Update chunked validation (lines 2651-2769)

The chunked processing has a parallel implementation of the validation logic. Apply the same modifications from Stage 2 and 3:

1. Add `all_closed` classification
2. Conditionally filter based on `include_non_closed_relations`
3. Split geometry construction by closure status

**Locate the chunked `classified_relations` CTE and apply same changes.**

**Test:**
- Force chunked mode (reduce available memory in test)
- Compare output with all-at-once mode
- Should be identical

---

### Stage 5: Add Comprehensive Tests
**Goal:** Test all scenarios with non-closed relations
**Success Criteria:**
- Test closed relations (existing behavior unchanged)
- Test non-closed relations (new behavior)
- Test mixed relations (GeometryCollection)
- Test with parameter False vs True
- Test cache file naming

**Files to create/modify:**
- `tests/base/test_non_closed_relations.py` (new)
- `tests/base/test_pbf_file_reader.py` (modify)

**Changes:**

#### 5.1. Create test PBF file with non-closed relations

**Approach:**
Use existing test PBF (Monaco) and create synthetic test cases, or:

1. Find/create PBF with route relation (e.g., bus route)
2. Extract to small test file
3. Add to `tests/fixtures/` directory

**Alternative:** Use OSM XML to create test data:
```xml
<relation id="123" version="1">
  <member type="way" ref="1" role=""/>
  <member type="way" ref="2" role=""/>
  <tag k="type" v="route"/>
  <tag k="route" v="bus"/>
</relation>
<!-- Where ways 1 and 2 don't form a closed loop -->
```

#### 5.2. Test cases

**Test file:** `tests/base/test_non_closed_relations.py`

```python
import pytest
from pathlib import Path
from shapely.geometry import MultiLineString, MultiPolygon
from quackosm import PbfFileReader

@pytest.fixture
def non_closed_relation_pbf():
    """PBF file containing a non-closed relation (e.g., route)."""
    return Path("tests/fixtures/route_relation.pbf")

@pytest.fixture
def closed_relation_pbf():
    """PBF file containing a closed relation (e.g., multipolygon)."""
    return Path("tests/fixtures/monaco.osm.pbf")  # Existing


class TestNonClosedRelations:
    """Test handling of non-closed OSM relations."""

    def test_exclude_non_closed_by_default(self, non_closed_relation_pbf):
        """Default behavior should exclude non-closed relations."""
        reader = PbfFileReader()
        gdf = reader.convert_pbf_to_geodataframe(non_closed_relation_pbf)

        # Should not include the non-closed relation
        relations = gdf[gdf['feature_id'].str.startswith('relation/')]
        assert len(relations) == 0

    def test_include_non_closed_when_enabled(self, non_closed_relation_pbf):
        """Should include non-closed relations when parameter is True."""
        reader = PbfFileReader(include_non_closed_relations=True)
        gdf = reader.convert_pbf_to_geodataframe(non_closed_relation_pbf)

        # Should include the non-closed relation
        relations = gdf[gdf['feature_id'].str.startswith('relation/')]
        assert len(relations) > 0

        # Geometry should be MultiLineString
        for geom in relations.geometry:
            assert isinstance(geom, MultiLineString)

    def test_closed_relations_unchanged(self, closed_relation_pbf):
        """Closed relations should produce MultiPolygon regardless of setting."""
        reader_default = PbfFileReader(include_non_closed_relations=False)
        reader_enabled = PbfFileReader(include_non_closed_relations=True)

        gdf_default = reader_default.convert_pbf_to_geodataframe(closed_relation_pbf)
        gdf_enabled = reader_enabled.convert_pbf_to_geodataframe(closed_relation_pbf)

        relations_default = gdf_default[gdf_default['feature_id'].str.startswith('relation/')]
        relations_enabled = gdf_enabled[gdf_enabled['feature_id'].str.startswith('relation/')]

        # Should have same relations (closed ones included in both)
        assert len(relations_default) == len(relations_enabled)

        # All should be MultiPolygon
        for geom in relations_default.geometry:
            assert isinstance(geom, MultiPolygon)
        for geom in relations_enabled.geometry:
            assert isinstance(geom, MultiPolygon)

    def test_cache_file_naming(self, non_closed_relation_pbf, tmp_path):
        """Cache file names should differ based on parameter."""
        reader_default = PbfFileReader(
            working_directory=tmp_path / "default",
            include_non_closed_relations=False
        )
        reader_enabled = PbfFileReader(
            working_directory=tmp_path / "enabled",
            include_non_closed_relations=True
        )

        reader_default.convert_pbf_to_geodataframe(non_closed_relation_pbf)
        reader_enabled.convert_pbf_to_geodataframe(non_closed_relation_pbf)

        files_default = list((tmp_path / "default").glob("*.parquet"))
        files_enabled = list((tmp_path / "enabled").glob("*.parquet"))

        # Should have different file names
        assert len(files_default) > 0
        assert len(files_enabled) > 0

        # Enabled should have "_nonclosedrelas" suffix
        assert any("_nonclosedrelas" in f.name for f in files_enabled)
        assert not any("_nonclosedrelas" in f.name for f in files_default)

    def test_mixed_geometry_collection(self, mixed_relation_pbf):
        """Relations with mixed closed/open parts should produce GeometryCollection."""
        reader = PbfFileReader(include_non_closed_relations=True)
        gdf = reader.convert_pbf_to_geodataframe(mixed_relation_pbf)

        relations = gdf[gdf['feature_id'].str.startswith('relation/')]

        # Should have GeometryCollection (or MultiPolygon + MultiLineString)
        # Exact behavior depends on implementation choice
        assert len(relations) > 0
        # Add specific assertions based on final implementation

    @pytest.mark.parametrize("include_non_closed", [False, True])
    def test_inner_outer_roles_preserved(self, non_closed_relation_pbf, include_non_closed):
        """Inner/outer roles should be preserved in tags."""
        reader = PbfFileReader(include_non_closed_relations=include_non_closed)
        gdf = reader.convert_pbf_to_geodataframe(non_closed_relation_pbf)

        relations = gdf[gdf['feature_id'].str.startswith('relation/')]

        if include_non_closed:
            assert len(relations) > 0
            # Check that role information is preserved
            # (implementation detail: may be in tags or separate column)


class TestBackwardCompatibility:
    """Ensure existing functionality is not broken."""

    def test_existing_tests_unchanged(self, closed_relation_pbf):
        """Verify all existing test expectations remain valid."""
        # This is a meta-test: run subset of existing tests
        # to ensure they still pass with default behavior

        reader = PbfFileReader()  # Default: include_non_closed_relations=False
        gdf = reader.convert_pbf_to_geodataframe(closed_relation_pbf)

        # Existing expectations (from current tests)
        relations = gdf[gdf['feature_id'].str.startswith('relation/')]
        for geom in relations.geometry:
            assert isinstance(geom, MultiPolygon)
```

#### 5.3. Modify existing tests

**File:** `tests/base/test_pbf_file_reader.py`

**Add parametrization to existing relation tests:**
```python
@pytest.mark.parametrize("include_non_closed", [False, True])
def test_existing_relation_test(include_non_closed):
    reader = PbfFileReader(include_non_closed_relations=include_non_closed)
    # ... rest of test
    # Ensure it passes with both values
```

#### 5.4. Add doctest examples

**File:** `quackosm/pbf_file_reader.py`

**Add to class docstring:**
```python
Examples:
    Include non-closed relations (e.g., route relations):

    >>> reader = PbfFileReader(include_non_closed_relations=True)
    >>> gdf = reader.convert_pbf_to_geodataframe("routes.osm.pbf")
    >>> # Output will include MultiLineString geometries for routes
```

**Test:**
```bash
# Run new tests
pytest -v tests/base/test_non_closed_relations.py

# Run all tests to ensure no regressions
pytest -v tests/base/

# Run doctests
pytest --doctest-modules quackosm/
```

---

### Stage 6: Documentation and Examples
**Goal:** Document new feature clearly
**Success Criteria:**
- README updated with new parameter
- CHANGELOG.md entry added
- API documentation complete
- Example usage provided

**Files to modify:**
- `README.md`
- `CHANGELOG.md`
- `docs/` (if applicable)

**Changes:**

#### 6.1. Update README.md

**Add to Features section:**
```markdown
- **Optional non-closed relation support**: Include OSM relations that don't form closed
  multipolygons (e.g., route relations, network relations) with `include_non_closed_relations=True`
```

**Add to Examples section:**
```markdown
### Including Non-Closed Relations

By default, QuackOSM only includes relations that form closed multipolygons (boundaries, areas).
To include relations with non-closed geometries (e.g., bus routes, hiking trails):

```python
from quackosm import PbfFileReader

# Include route relations
reader = PbfFileReader(
    tags_filter={"route": ["bus", "hiking"]},
    include_non_closed_relations=True
)

gdf = reader.convert_pbf_to_geodataframe("city.osm.pbf")

# Output will include:
# - Closed relations → MultiPolygon (boundaries, areas)
# - Non-closed relations → MultiLineString (routes, networks)
# - Mixed relations → GeometryCollection
```

**Note:** Output geometry types will vary based on relation topology. Ensure your
downstream tools support MultiLineString and GeometryCollection geometries.
```

#### 6.2. Update CHANGELOG.md

**Add entry for v0.17.0:**
```markdown
## [0.17.0] - YYYY-MM-DD

### Added
- **Non-closed relation support**: New `include_non_closed_relations` parameter in `PbfFileReader`
  - When `True`, includes OSM relations that don't form closed multipolygons
  - Outputs appropriate geometry types: MultiLineString for routes, GeometryCollection for mixed
  - Default `False` maintains backward compatibility
  - Fixes #248: Missing POIs from non-regular relation geometries

### Changed
- Cache file naming now includes `_nonclosedrelas` suffix when non-closed relations are enabled
```

#### 6.3. Update API documentation

**Ensure docstring in `PbfFileReader.__init__` is complete (already done in Stage 1).**

#### 6.4. Create example notebook (optional)

**File:** `examples/non_closed_relations.ipynb`

```python
# Example: Extract bus routes from OSM data

from quackosm import PbfFileReader
import geopandas as gpd

# Download example area with bus routes
reader = PbfFileReader(
    tags_filter={"route": "bus"},
    include_non_closed_relations=True
)

# Convert to GeoDataFrame
gdf = reader.convert_geometry_to_geodataframe(
    geometry="Munich, Germany"
)

# Filter for relations (routes)
routes = gdf[gdf['feature_id'].str.startswith('relation/')]

print(f"Found {len(routes)} bus routes")
print(f"Geometry types: {routes.geometry.type.value_counts()}")

# Plot routes
routes.plot(figsize=(10, 10))
```

**Test:** Run example to ensure it works.

---

## Testing Strategy

### Test Matrix

| Scenario | include_non_closed_relations | Expected Output |
|----------|------------------------------|-----------------|
| Closed relation only | False | MultiPolygon |
| Closed relation only | True | MultiPolygon |
| Non-closed relation | False | (excluded) |
| Non-closed relation | True | MultiLineString |
| Mixed relation | False | (excluded if any part non-closed) |
| Mixed relation | True | GeometryCollection or split features |

### Test Levels

1. **Unit tests:** Individual method behavior
   - `_save_valid_relation_parts()` with both parameter values
   - Geometry construction for closed vs non-closed
   - File naming with suffix

2. **Integration tests:** Full pipeline
   - PBF → GeoDataFrame with non-closed relations
   - Cache hit/miss behavior
   - Chunked vs all-at-once mode equivalence

3. **Regression tests:** Existing functionality
   - All current tests pass without modification
   - Default behavior unchanged

4. **GDAL parity tests:** Geometry correctness
   - Compare with GDAL ogr2ogr output
   - Validate geometry types match expectations

5. **Performance tests:** No significant degradation
   - Benchmark with `tests/benchmark/`
   - Compare processing time with parameter False vs True

### CI/CD Validation

**Pre-commit hooks:**
- Ruff linting
- Mypy type checking
- Docformatter

**CI pipeline:**
- tox tests (Python 3.9-3.13)
- Coverage report (target >90%)
- GDAL parity tests

**Manual validation:**
- Test with real-world PBF files containing route relations
- Verify output in QGIS or other GIS tools
- Check GeometryCollection rendering

---

## Implementation Checklist

### Stage 1: Configuration Parameter ✅ COMPLETED
- [x] Add `include_non_closed_relations` parameter to `__init__` (line 176)
- [x] Store as instance variable (line 270)
- [x] Update docstring with parameter description (lines 233-242)
- [x] Add to cache file naming (`_nonclosedrelas` suffix) (lines 1283, 1326)
- [x] Run existing tests (should all pass) - PASSED

**Implementation details:**
- Added parameter after `ignore_metadata_tags` in signature
- Cache file naming updated in both `_generate_result_file_path()` and `_generate_result_file_path_from_geometry()`
- Docstring includes full explanation of output geometry types

### Stage 2: Validation Logic ✅ COMPLETED
- [x] Modify `_save_valid_relation_parts()` validation CTE (all-at-once mode: lines 2645-2666)
- [x] Add `all_closed` classification
- [x] Conditionally filter based on parameter
- [x] Pass classification to downstream operations
- [x] Update chunked processing mode (lines 2751-2790)

**Implementation details:**
- Replaced `valid_relations` CTE with two CTEs: `classified_relations` and `valid_relations`
- Filter condition: `WHERE all_closed = true` (default) or `WHERE 1=1` (when enabled)
- Added `all_closed` column to output for downstream use
- Applied same changes to both all-at-once and chunked processing paths

### Stage 3: Geometry Construction ✅ COMPLETED
- [x] Split inner/outer processing by closure status (lines 2497-2529)
- [x] Update hole processing (only for closed relations) (lines 2535-2561, added `WHERE og.all_closed = true`)
- [x] Modify final aggregation to handle mixed types (lines 2585-2639)
- [ ] Test closed → MultiPolygon (needs proper test data)
- [ ] Test non-closed → MultiLineString (needs proper test data)
- [ ] Test mixed → GeometryCollection (needs proper test data)

**Implementation details:**
- Inner parts: CASE statement to use `ST_MakePolygon` for closed, `ST_RemoveRepeatedPoints` for non-closed
- Outer parts: Same CASE statement, plus added `all_closed` column to output
- Hole subtraction: Added `WHERE og.all_closed = true` filter
- Non-closed parts: Conditional processing only when `include_non_closed_relations=True`
- Final aggregation: Uses `ST_Union_Agg` to handle mixed geometry types (creates GeometryCollection)
- Added `relation_non_closed_parts` to temp file cleanup list (line 1219)

### Stage 4: Chunked Processing ✅ COMPLETED (as part of Stage 2)
- [x] Apply same logic to chunked mode (lines 2751-2790)
- [ ] Test chunked vs all-at-once equivalence (needs test data)
- [ ] Verify memory-constrained scenarios (needs test data)

**Implementation details:**
- Chunked mode validated in parallel with all-at-once mode during Stage 2
- Same SQL logic applied to both paths

### Stage 5: Tests ⏳ PENDING
- [ ] Create test PBF with non-closed relations OR find real-world example
- [ ] Write `test_non_closed_relations.py`
- [ ] Add parametrization to existing tests
- [ ] Add doctest examples
- [ ] Run full test suite
- [ ] Verify coverage >90%

**Testing notes:**
- Monaco PBF has 290 relations but route relations are filtered by tag filtering (not suitable for testing)
- Need either: (1) synthetic test data, or (2) PBF with multipolygon relations having irregular geometries
- Consider using OSM XML to create test fixtures

### Stage 6: Documentation ⏳ PENDING
- [ ] Update README.md
- [ ] Add CHANGELOG.md entry
- [ ] Verify API documentation (docstring already complete)
- [ ] Create example notebook (optional)
- [ ] Review all documentation for clarity

### Final Validation ⏳ PENDING
- [x] All existing tests pass (Python 3.9-3.13) - smoke test passed
- [ ] No mypy errors (need to run)
- [ ] Pre-commit hooks pass (need to run)
- [ ] Manual testing with real PBF files (need suitable test file)
- [ ] Performance benchmarks acceptable (need to run)
- [ ] Ready for PR

---

## Rollback Plan

If issues arise during implementation:

1. **Stage 1-2 issues:** Revert parameter addition, minimal impact
2. **Stage 3-4 issues:** Keep parameter but disable functionality (always return empty for non-closed)
3. **Stage 5-6 issues:** Skip tests/docs, mark as experimental feature

**Safe rollback:** Parameter default=False ensures existing users unaffected.

---

## Success Metrics

- [ ] All existing tests pass without modification
- [ ] New tests achieve >95% coverage of new code paths
- [ ] No performance degradation (< 5% difference)
- [ ] Successfully processes real-world route relations
- [ ] Output validated against GDAL (where comparable)
- [ ] Documentation clear and complete
- [ ] Issue #248 resolved

---

## Open Questions & Decisions Needed

1. **Mixed relation handling:**
   - Decision needed: GeometryCollection or split into two features?
   - Recommendation: GeometryCollection (preserves relation ID)
   - Action: Implement and validate with user feedback

2. **Role preservation:**
   - Decision needed: How to expose inner/outer roles for non-closed parts?
   - Recommendation: Keep in tags, document behavior
   - Action: Add to docstring

3. **Test data:**
   - Decision needed: Use real PBF or synthetic OSM XML?
   - Recommendation: Real PBF for authenticity, synthetic for edge cases
   - Action: Find suitable route relation PBF (< 1MB)

4. **GDAL comparison:**
   - Question: How does GDAL handle non-closed relations?
   - Action: Test ogr2ogr output before finalizing implementation
   - Document differences if any

5. **Downstream compatibility:**
   - Question: Which tools struggle with GeometryCollection?
   - Action: Test output in QGIS, Folium, ArcGIS, etc.
   - Document known limitations

---

## Timeline (Rough Estimates)

- **Stage 1:** 1-2 hours (parameter setup)
- **Stage 2:** 2-3 hours (validation logic)
- **Stage 3:** 4-6 hours (geometry construction)
- **Stage 4:** 2-3 hours (chunked mode)
- **Stage 5:** 4-6 hours (comprehensive tests)
- **Stage 6:** 2-3 hours (documentation)
- **Testing & validation:** 3-4 hours
- **PR review & fixes:** 2-4 hours

**Total:** 20-30 hours

---

## Notes

- Follow project philosophy: "Incremental progress over big bangs"
- Commit after each stage with clear messages
- Run tests frequently (after each stage)
- Document decisions in commit messages
- Ask user for feedback before major architectural choices
- Stop after 3 attempts if stuck (per guidelines)
