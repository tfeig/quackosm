# Relation Extraction Improvements

**Status**: Implemented (2026-01)
**Affects**: Relation processing, geometry extraction, output completeness

---

## Problem Statement

QuackOSM previously excluded several categories of OSM relations from the extraction output:

1. **Non-boundary/multipolygon relations**: Relations with `type=site`, `type=route`, `type=network`, etc. were filtered out regardless of whether they had valid geometries.

2. **Node-only relations**: Relations containing only node members (no ways) were completely excluded during validation, even when nodes were valid.

3. **Nested relation visibility**: Relations containing sub-relations provided no indication of this structure, making it difficult for users to understand incomplete geometries.

### Real-World Impact

These limitations affected common OSM features:
- **Universities and campuses** (`type=site`) with building locations
- **Bus/train routes** (`type=route`) representing transit lines
- **Transit networks** (`type=network`, `type=route_master`) organizing routes
- **Turn restrictions** (`type=restriction`) for navigation
- **Administrative collections** without physical boundaries

## Solutions Implemented

Three complementary features address these limitations:

### 1. Include Non-Closed Relations (`include_non_closed_relations`)

**Type**: Optional parameter (default: `False`)
**Added to**: `PbfFileReader` and all convenience functions

#### What It Does

When enabled, includes all OSM relation types instead of only `type=boundary` and `type=multipolygon`.

#### Technical Implementation

- **Root cause**: Hardcoded type filter at Step 11 (relation reading) in `pbf_file_reader.py:1657-1668`
- **Solution**: Made type filter conditional based on parameter value
- **Geometry handling**: Uses `CASE` statements to create appropriate geometry types:
  - Closed rings → `ST_MakePolygon` → Polygon/MultiPolygon
  - Non-closed rings → `ST_RemoveRepeatedPoints` → LineString/MultiLineString
  - Mixed → `ST_Union_Agg` → GeometryCollection

#### Output Geometry Types

| Relation Structure | `include_non_closed_relations=False` | `include_non_closed_relations=True` |
|-------------------|-------------------------------------|-------------------------------------|
| All parts closed | Polygon/MultiPolygon | Polygon/MultiPolygon |
| All parts non-closed | Excluded | LineString/MultiLineString |
| Mixed closed/non-closed | Excluded | GeometryCollection |

#### Cache Naming

Files include `_nonclosedrelas` suffix when parameter is enabled.

#### Known Limitations

- **Nested relations not resolved**: Only direct way members are processed. Relations with sub-relation members will have incomplete geometries (see Feature 3).
- **Performance impact**: Processing all relation types increases extraction time proportionally to additional relations included.

### 2. Include Node-Only Relations (`include_node_only_relations`)

**Type**: Optional parameter (default: `False`)
**Added to**: `PbfFileReader` and all convenience functions

#### What It Does

When enabled, includes relations that have only node members (no ways) as Point or MultiPoint geometries.

#### Technical Implementation

- **Root cause**: Validation logic in `pbf_file_reader.py:1746-1801` only checked way-based relations
- **Solution**: Added parallel processing path for node-only relations:
  1. Detect relations with zero way members
  2. Extract node references
  3. Validate against all available nodes (not filtered nodes)
  4. Construct Point (single node) or MultiPoint (multiple nodes) geometries
- **Key insight**: Node members don't need to match tag filters (similar to how way nodes are handled)

#### Output Geometry Types

| Node Members | Output Geometry |
|--------------|-----------------|
| Single node | Point |
| Multiple nodes | MultiPoint |

#### Cache Naming

Files include `_nodeonlyrelas` suffix when parameter is enabled.

#### Use Cases

- **University campuses** (`type=site`) with building/department location markers
- **Network nodes** (`type=network`) showing junction points
- **Administrative markers** (`type=land_area`) for territory boundaries

#### Known Limitations

- **Sub-relations ignored**: Similar to Feature 1, only direct node members are processed.
- **Node roles not exposed**: Member roles are extracted but not included in output tags.

### 3. Nested Relation IDs Tag (`quackosm:nested_relation_ids`)

**Type**: Synthetic tag (automatically added)
**Applied to**: All relations with sub-relation members

#### What It Does

Adds a comma-separated list of nested relation IDs to relations that contain sub-relations, providing visibility into hierarchical structures.

#### Technical Implementation

Location: `pbf_file_reader.py:1725-1763`

```sql
WITH nested_relation_ids AS (
    SELECT
        id,
        STRING_AGG(CAST(ref AS VARCHAR), ',') as sub_rel_ids
    FROM unnested_relation_refs
    WHERE ref_type = 'relation'
    GROUP BY id
),
tags_with_sub_relations AS (
    SELECT
        ft.id,
        CASE
            WHEN sri.sub_rel_ids IS NOT NULL
            THEN map_concat(ft.tags, map(['quackosm:nested_relation_ids'], [sri.sub_rel_ids]))
            ELSE ft.tags
        END as tags
    FROM filtered_tags ft
    LEFT JOIN nested_relation_ids sri ON ft.id = sri.id
)
```

#### Example Output

For relation 13128906 (Europa-Universität Viadrina):
```python
{
    'name': 'Europa-Universität Viadrina',
    'type': 'site',
    'amenity': 'university',
    'quackosm:nested_relation_ids': '13128905'  # Nested relation ID
}
```

#### Usage

Users can identify relations with incomplete geometries:

```python
import geopandas as gpd

gdf = gpd.read_parquet('output.parquet')
relations = gdf[gdf.index.str.startswith('relation/')]

# Find relations with nested sub-relations
with_nested = relations[
    relations['tags'].apply(lambda x: 'quackosm:nested_relation_ids' in dict(x))
]

# Extract nested IDs for further processing
for idx, row in with_nested.iterrows():
    nested_ids = dict(row['tags'])['quackosm:nested_relation_ids'].split(',')
    print(f"{idx} has nested relations: {nested_ids}")
```

#### Tag Naming Convention

- **Namespace**: `quackosm:` clearly identifies synthetic tags
- **Format**: Comma-separated relation IDs (e.g., `"123,456,789"`)
- **Scope**: Only added to relations that have at least one sub-relation member

#### Performance Impact

Minimal - adds one CTE and LEFT JOIN during relation processing.

## Design Decisions

### Why Optional Parameters?

Both `include_non_closed_relations` and `include_node_only_relations` default to `False` to maintain backward compatibility. Users must explicitly opt in to include these relation types.

**Rationale**:
- Existing workflows and tests remain unchanged
- Performance cost only paid when needed
- Clear user intent required for potentially incomplete geometries

### Why Not Resolve Nested Relations?

Full nested relation resolution would require:
1. Recursive processing (resolve sub-relations before parents)
2. Cycle detection (prevent infinite loops)
3. Depth handling (multi-level nesting)
4. Memory management (large hierarchies)
5. Geometry merging (combine sub-relation geometries)

**Estimated complexity**: Multiple days of development + extensive testing

**Decision**: Document the limitation and provide visibility via synthetic tag. Users who need complete geometries can:
- Use the nested relation IDs to extract sub-relations separately
- Post-process geometries using OSM API
- Flatten relation hierarchies at the data source level

### Why Validate Node-Only Relations Against All Nodes?

Node members of relations serve different purposes than filtered nodes:
- **Way nodes**: Define geometry shape (not semantic features)
- **Relation nodes**: Can be semantic (location markers) or structural

**Decision**: Treat relation nodes like way nodes - validate they exist, but don't require them to match tag filters. The relation's tags determine filtering, not member tags.

## Testing

### Test Coverage

Added comprehensive test suite: `tests/base/test_relation_features.py`

- 16 tests covering all three features
- Tests both enabled/disabled states
- Validates cache file naming
- Verifies geometry types
- Tests parameter combinations
- Confirms backward compatibility

### Test Data

Uses Monaco PBF (standard test file) which contains:
- 142 relations (with features enabled)
- 6 node-only relations (site, land_area, treaty types)
- 54 relations with nested sub-relations
- 62 route relations (non-closed)

### Validation Results

Example: Brandenburg PBF (brandenburg-latest.osm.pbf)

| Metric | Default | With Features | Change |
|--------|---------|---------------|--------|
| Total Relations | 23,127 | 40,507 | +17,380 (+75%) |
| Polygon | 22,364 | 25,534 | +3,170 |
| MultiPolygon | 763 | 2,002 | +1,239 |
| LineString | 0 | 7,492 | +7,492 ✨ |
| MultiLineString | 0 | 5,464 | +5,464 ✨ |
| GeometryCollection | 0 | 15 | +15 ✨ |
| Point/MultiPoint | 0 | Variable | Node-only relations ✨ |

## Migration Guide

### For Existing Users

No action required - default behavior is unchanged.

### To Include All Relation Types

```python
from quackosm import PbfFileReader

reader = PbfFileReader(
    include_non_closed_relations=True,
    include_node_only_relations=True,
)

gdf = reader.convert_pbf_to_geodataframe("city.osm.pbf")
```

### To Identify Incomplete Geometries

```python
# Find relations with nested sub-relations
relations = gdf[gdf.index.str.startswith('relation/')]
incomplete = relations[
    relations['tags'].apply(
        lambda x: 'quackosm:nested_relation_ids' in dict(x)
    )
]

# Process nested relations separately if needed
for idx, row in incomplete.iterrows():
    nested_ids = dict(row['tags'])['quackosm:nested_relation_ids'].split(',')
    # Extract nested relations from PBF or OSM API
```

## Future Enhancements

### Nested Relation Resolution

Could be implemented as a separate post-processing step:
- Input: GeoDataFrame with `quackosm:nested_relation_ids` tags
- Process: Recursively resolve sub-relations
- Output: Enhanced geometries with nested structures

This would keep the core extraction simple while allowing advanced users to opt into complex resolution.

### Mixed Node/Way Relations

Currently, relations with both node and way members only process ways. Enhancement could:
- Include both way geometries AND node points
- Output: `GeometryCollection(MultiPolygon + MultiPoint)`
- Use case: Complex facilities with buildings (ways) and entry points (nodes)

### Node Role Exposure

Could add member roles to output:
- As separate column: `node_roles`
- As expanded tags: `node_role:123456 = "entrance"`
- Use case: Understanding node function within relation

## References

- **Implementation**: `quackosm/pbf_file_reader.py` (lines 176, 233-248, 270, 1283, 1326, 1657-1668, 1725-1763, 1746-1801, 2497-2790)
- **Public API**: `quackosm/functions.py` (all 9 convenience functions)
- **Tests**: `tests/base/test_relation_features.py`
- **OSM Relation Types**: https://wiki.openstreetmap.org/wiki/Relations

---

**Contributors**: Implementation completed January 2026
**Version**: 0.17.0 (proposed)
