# Nested Relation IDs Implementation Summary

**Date:** 2026-01-16
**Feature:** Add synthetic tag for nested relation IDs in exported parquet files

---

## Problem Statement

QuackOSM correctly identifies relations that contain nested relations (nested relations) but does not include the nested relation geometries in the parent relation's geometry. This was documented in the previous investigation where relation 13128906 (Europa-Universität Viadrina) has a nested relation 13128905 (Hauptgebäude) that isn't geometrically included.

While fully reconstructing nested relation geometries would be complex (requiring recursive resolution, cycle detection, etc.), users still need visibility into which relations have nested relations.

## Solution

Add a synthetic tag `quackosm:nested_relation_ids` to the exported parquet file's tags column. This tag contains a comma-separated list of all nested relation IDs for relations that have nested relations.

### Example

For relation 13128906 (Europa-Universität Viadrina), the exported parquet will include:
```python
{
    'name': 'Europa-Universität Viadrina',
    'type': 'site',
    'amenity': 'university',
    ...
    'quackosm:nested_relation_ids': '13128905'  # ← New synthetic tag
}
```

## Implementation Details

### Code Changes

**File:** `quackosm/pbf_file_reader.py:1725-1763`

Modified the `relations_all_with_tags` query to:

1. **Extract nested relation IDs** - Unnest the relation refs and filter for `ref_type = 'relation'`
2. **Aggregate as comma-separated string** - Use `STRING_AGG()` to create "123,456,789" format
3. **Merge into tags map** - Use `map_concat()` to add the synthetic tag to existing tags

```sql
WITH unnested_relation_refs AS (
    SELECT
        r.id,
        UNNEST(refs) as ref,
        UNNEST(ref_types) as ref_type
    FROM relations r
),
nested_relation_ids AS (
    SELECT
        id,
        STRING_AGG(CAST(ref AS VARCHAR), ',') as sub_rel_ids
    FROM unnested_relation_refs
    WHERE ref_type = 'relation'
    GROUP BY id
),
filtered_tags AS (
    SELECT id, {filtered_tags_clause}
    FROM relations r
    WHERE tags IS NOT NULL AND cardinality(tags) > 0
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
SELECT id, tags
FROM tags_with_sub_relations
WHERE tags IS NOT NULL AND cardinality(tags) > 0
```

### Tag Naming Convention

We use the namespace `quackosm:` to clearly identify synthetic tags added by QuackOSM and avoid conflicts with actual OSM tags. The tag name `nested_relation_ids` was chosen because:
- "Nested" clearly conveys the hierarchical structure
- It matches common OSM terminology
- It's more descriptive and less ambiguous than alternatives like "nested relation"

## Testing

### Test Scripts Created

1. **test_nested_relation_ids.py** - General test for any PBF file
2. **test_check_sub_relations.py** - Diagnostic to check if nested relations exist in PBF
3. **test_check_intermediate_tags.py** - Inspect intermediate parquet files
4. **test_sql_logic_directly.py** - Verify SQL logic works correctly
5. **test_specific_relation.py** - Test specific relation with geometry filter
6. **test_detailed_tags.py** - Detailed tag inspection (final verification)

### Verification Results

**Relation 13128906 (Europa-Universität Viadrina):**
- ✅ Found in exported parquet
- ✅ Has `quackosm:nested_relation_ids` tag
- ✅ Tag value: `13128905` (correct nested relation ID)
- ✅ All original OSM tags preserved

**Other test cases:**
- ✅ Relations without nested relations: No synthetic tag added (as expected)
- ✅ Relations with multiple nested relations: Comma-separated list works correctly
- ✅ Examples found: route_master, superroute, site relations with nested structures

## Usage

Users can now:

1. **Identify relations with nested relations:**
   ```python
   import geopandas as gpd

   gdf = gpd.read_parquet('output.parquet')
   relations = gdf[gdf['feature_id'].str.startswith('relation/')]

   # Find relations with nested relations
   with_sub_rels = relations[
       relations['tags'].apply(
           lambda x: 'quackosm:nested_relation_ids' in dict(x)
       )
   ]
   ```

2. **Extract nested relation IDs:**
   ```python
   for idx, row in with_sub_rels.iterrows():
       tags = dict(row['tags'])
       sub_rel_ids = tags['quackosm:nested_relation_ids'].split(',')
       print(f"{row['feature_id']} has nested relations: {sub_rel_ids}")
   ```

3. **Fetch complete geometries separately:**
   Users can now identify which relations need additional processing and fetch the nested relations separately using the OSM API or by extracting them from the PBF file.

## Performance Impact

**Minimal:** The feature adds one additional SQL CTE and LEFT JOIN during the relation processing phase. The overhead is negligible compared to the overall PBF conversion time.

## Future Enhancements

If full nested relation geometry reconstruction is implemented in the future, this tag provides a foundation for:
- Detecting which relations need recursive processing
- Validating that all nested relations were successfully resolved
- Debugging missing or incomplete geometries

## Backward Compatibility

✅ **Fully backward compatible**
- Existing code continues to work unchanged
- The synthetic tag is just another entry in the tags map
- Relations without nested relations are unaffected
- Tag filtering still works normally (synthetic tag can be excluded if needed)

## Documentation

No documentation changes required at this time since:
- The feature is self-explanatory (tag name clearly indicates purpose)
- It's a data enhancement, not an API change
- Users who need it will discover it naturally when inspecting tags

If this feature proves valuable, future documentation could include:
- Mention in relation processing section
- Example notebooks showing nested relation handling
- Section in troubleshooting guide about incomplete relation geometries

---

## Conclusion

The implementation successfully adds nested relation IDs as a synthetic tag in the exported parquet files. This provides transparency about nested relation structures without the complexity of full geometric reconstruction.

Users can now:
- ✅ Know which relations have nested relations
- ✅ Identify specific nested relation IDs
- ✅ Make informed decisions about additional processing
- ✅ Debug incomplete geometries more effectively

**Status:** ✅ Complete and verified
