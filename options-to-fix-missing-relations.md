# Options to Fix Missing Relations (Non-Regular Geometries)

## Problem Statement

QuackOSM currently excludes OSM relations that don't form closed multipolygons. As reported in [issue #248](https://github.com/kraina-ai/quackosm/issues/248), some expected POIs are missing from parquet files because they are relations with "complicated" or non-regular geometries.

The issue states: "only boundaries and areas that create closed multipolygon are selected"

## Current Implementation

### Where the Limitation Occurs

**File:** `quackosm/pbf_file_reader.py`
**Location:** Lines 2635-2640 in `_save_valid_relation_parts()`

```sql
SELECT
    id,
    bool_and(
        ST_Equals(ST_StartPoint(geometry), ST_EndPoint(geometry))
    ) is_valid
FROM relations_with_geometries
GROUP BY id
WHERE is_valid = true  -- Only keeps relations where ALL parts are closed
```

This validation ensures **every linestring part** in a relation forms a closed ring (start point = end point). If even one part is open, the entire relation is excluded from output.

### Pipeline Context

The validation happens at **Step 25** of the 32-step processing pipeline:
- **Step 25:** Save Valid Relation Parts (filters non-closed)
- **Step 26:** Save Relation Inner Parts (holes)
- **Step 27:** Save Relation Outer Parts (boundaries)
- **Step 28:** Save Relation Outer Parts with Holes
- **Step 29:** Save Relation Outer Parts without Holes
- **Step 30:** Save Final Relation Geometries (MultiPolygon output)

### Why This Limitation Exists

The current implementation assumes:
1. All OSM relations represent areas (polygons)
2. Areas require closed boundaries (valid topology)
3. Output geometry type is always `MultiPolygon`

This is correct for most OSM relations (administrative boundaries, building complexes, multipolygon areas), but excludes valid use cases:
- Route relations (bus routes, hiking trails) - naturally non-closed
- Network relations (road networks, waterways) - may have open segments
- Complex boundary relations with irregular topology

## Feasibility Assessment

### ✅ Technically Feasible

**Supporting evidence:**
1. **Geometry already reconstructed:** Relation way geometries are already built as LineStrings (lines 2582-2769)
2. **DuckDB spatial support:** DuckDB supports `MultiLineString`, `GeometryCollection`, and mixed geometry types
3. **Infrastructure in place:** Complex relation handling (inner/outer roles, holes) already implemented
4. **Valid use case:** OpenStreetMap allows non-closed relations by design

### ⚠️ Implementation Challenges

1. **Output geometry type variability:**
   - Current: All relations → `MultiPolygon`
   - Needed: Relations → `MultiPolygon`, `MultiLineString`, or `GeometryCollection`

2. **Mixed geometry relations:**
   - Some parts closed (can form Polygons)
   - Some parts open (remain LineStrings)
   - How to represent in output?

3. **Backward compatibility:**
   - Existing users expect only `MultiPolygon` geometries
   - Tools consuming output may not handle `GeometryCollection`
   - Need opt-in behavior to avoid breaking changes

4. **File format implications:**
   - GeoParquet supports mixed geometries
   - Some geospatial tools struggle with `GeometryCollection`
   - Output files may not work with all downstream consumers

5. **Cache file naming:**
   - Hash-based naming must reflect this new parameter
   - Existing caches won't work with new geometry types

## Proposed Implementation Approaches

### Option 1: Configuration Parameter (⭐ Recommended)

**Add parameter:** `include_non_closed_relations: bool = False`

**Behavior:**
- `False` (default): Current behavior - only closed MultiPolygons
- `True`: Include all relations with appropriate geometry types

**Geometry type strategy:**
```python
# All parts closed → MultiPolygon (current behavior)
# All parts open → MultiLineString (new)
# Mixed open/closed → GeometryCollection or split into two features
```

**Pros:**
- ✅ Maintains backward compatibility (default unchanged)
- ✅ Clear user control and expectations
- ✅ Explicit about output geometry types
- ✅ Simpler implementation than auto-detection
- ✅ Can be documented clearly in API

**Cons:**
- ⚠️ Users must know to enable it
- ⚠️ Two code paths to maintain

**Implementation complexity:** Medium

---

### Option 2: Geometry Type Auto-Detection

**Behavior:**
- Automatically detect geometry type per relation
- Output appropriate type without user configuration

**Detection logic:**
```python
for each relation:
    if all_parts_closed:
        output_type = MultiPolygon
    elif all_parts_open:
        output_type = MultiLineString
    else:  # mixed
        output_type = GeometryCollection or split features
```

**Pros:**
- ✅ No user configuration needed
- ✅ Single code path
- ✅ Handles all cases automatically

**Cons:**
- ⚠️ Breaking change for existing users
- ⚠️ Output geometry type becomes unpredictable
- ⚠️ May break downstream tools expecting only MultiPolygon
- ⚠️ Harder to document expected behavior

**Implementation complexity:** Medium

---

### Option 3: Fallback Strategy with Try-Catch

**Behavior:**
- Try to build closed geometry first
- Fall back to linestring if validation fails

**Algorithm:**
```python
for each relation_part:
    try:
        geometry = ST_MakePolygon(part)  # Requires closed ring
    except:
        geometry = part  # Keep as LineString

aggregate:
    ST_Union_Agg(geometries)  # Handles mixed Polygon/LineString → GeometryCollection
```

**Pros:**
- ✅ Graceful degradation
- ✅ Maximizes polygon creation when possible
- ✅ Single unified code path

**Cons:**
- ⚠️ Breaking change (changes output type)
- ⚠️ Try-catch in SQL can be inefficient
- ⚠️ Error handling in DuckDB less predictable
- ⚠️ May hide actual data quality issues

**Implementation complexity:** High

---

### Option 4: Separate Processing Path

**Behavior:**
- Keep current closed-relation pipeline unchanged
- Add parallel pipeline for non-closed relations

**Flow:**
```
Relations → Split
  ├─ Closed Relations → Polygon Pipeline → MultiPolygon
  └─ Non-Closed Relations → LineString Pipeline → MultiLineString

Final Output: UNION ALL both pipelines
```

**Pros:**
- ✅ Zero risk to existing functionality
- ✅ Clean separation of concerns
- ✅ Easy to test independently

**Cons:**
- ⚠️ Code duplication
- ⚠️ Higher maintenance burden
- ⚠️ More complex overall architecture
- ⚠️ Still a breaking change (mixed output types)

**Implementation complexity:** High

## Recommendation

**Choose Option 1: Configuration Parameter**

**Rationale:**
1. **Backward compatibility:** Default behavior unchanged, zero risk to existing users
2. **User control:** Explicit opt-in with clear expectations
3. **Maintainability:** Single code path with conditional logic is easier than parallel pipelines
4. **Documentation:** Can clearly document what geometries to expect
5. **Testing:** Easier to test both modes independently
6. **Aligns with project philosophy:** "Pragmatic over dogmatic - Adapt to project reality"

## Code Changes Required

### 1. Core Files

**`quackosm/pbf_file_reader.py`:**
- Add `include_non_closed_relations: bool = False` to `PbfFileReader.__init__()` (~line 86)
- Modify `_save_valid_relation_parts()` (~line 2582) to conditionally skip closed-ring validation
- Update `_save_relation_outer_parts()` and `_save_relation_inner_parts()` to handle LineString outputs
- Modify final geometry aggregation (~line 2552) to handle mixed geometry types

### 2. File Naming Convention

**`quackosm/_osm_tags_filters.py`:**
- Add `_nonclosedrelas` suffix to cache filenames when `include_non_closed_relations=True`
- Example: `monaco_nofilter_noclip_compact_nonclosedrelas.parquet`

### 3. Tests

**New test file:** `tests/base/test_non_closed_relations.py`
- Test relations with all open linestrings → `MultiLineString`
- Test relations with all closed linestrings → `MultiPolygon` (existing behavior)
- Test mixed open/closed relations → `GeometryCollection`
- Test with `include_non_closed_relations=False` (excludes non-closed)
- Test with `include_non_closed_relations=True` (includes all)

### 4. Documentation

**Files to update:**
- `README.md` - Mention new parameter in features
- `CHANGELOG.md` - Add entry for new feature
- API documentation in docstrings
- Examples in `examples/` directory

## Example SQL Changes

**Current validation (lines 2629-2641):**
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
    WHERE is_valid = true  -- Excludes non-closed
)
```

**Proposed modification:**
```sql
classified_relations AS (
    SELECT
        id,
        bool_and(ST_Equals(ST_StartPoint(geometry), ST_EndPoint(geometry))) all_closed
    FROM relations_with_geometries
    GROUP BY id
),
valid_relations AS (
    SELECT id, all_closed
    FROM classified_relations
    WHERE {
        if include_non_closed_relations:
            "1=1"  -- Include all relations
        else:
            "all_closed = true"  -- Only closed relations (current behavior)
    }
)
```

Then split downstream processing:
```sql
-- For all_closed = true: Use ST_MakePolygon() → MultiPolygon
-- For all_closed = false: Keep as LineString → MultiLineString
-- Aggregate with ST_Union_Agg() which handles mixed types
```

## Migration Path

### Phase 1: Implementation (v0.17.0)
- Add parameter with default `False`
- Implement conditional logic
- Add tests
- Document in CHANGELOG

### Phase 2: User Adoption (v0.17.x - v0.18.x)
- Users opt-in with `include_non_closed_relations=True`
- Gather feedback on geometry types
- Identify edge cases

### Phase 3: Evaluation (v0.19.0+)
- Assess usage patterns
- Consider changing default if widely adopted
- Deprecation notice if changing default

## Performance Considerations

**Expected impact:**
- ✅ Minimal performance overhead (one additional boolean check in SQL)
- ✅ May reduce processing time by skipping validation for open relations
- ⚠️ Output file size may increase (more relations included)
- ⚠️ GeometryCollection may be slower to render in some tools

**Disk usage:**
- Unchanged for default behavior
- May increase 5-20% when including non-closed relations (depends on data)

## Open Questions

1. **Mixed relations handling:**
   - Option A: Create GeometryCollection with both Polygon and LineString parts
   - Option B: Split into two separate features (one MultiPolygon, one MultiLineString)
   - **Recommendation:** Option A (single feature, GeometryCollection) to preserve OSM relation ID mapping

2. **Inner/outer role for non-closed:**
   - Should we respect inner/outer roles for LineStrings?
   - **Recommendation:** Yes, preserve in tags but don't apply hole logic (only works for polygons)

3. **Geometry validation:**
   - Should we still run Shapely validation/fixing on LineStrings?
   - **Recommendation:** Yes, use `make_valid()` for all geometry types

4. **GDAL parity testing:**
   - How does GDAL handle non-closed relations?
   - **Action:** Test with GDAL ogr2ogr to establish expected behavior

## References

- Issue: https://github.com/kraina-ai/quackosm/issues/248
- OSM Relations: https://wiki.openstreetmap.org/wiki/Relation
- DuckDB Spatial Extension: https://duckdb.org/docs/extensions/spatial
- GeoParquet Spec: https://geoparquet.org/
