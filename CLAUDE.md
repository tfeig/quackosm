# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QuackOSM is a Python library for reading OpenStreetMap PBF files using DuckDB's spatial extension, converting OSM data to GeoParquet format without requiring GDAL. The library is production-ready with comprehensive testing, CI/CD, and memory-aware processing capabilities.

## Development Commands

### Package Management

QuackOSM uses **PDM** for dependency management:

```bash
# Install dependencies
pdm install

# Install with optional CLI dependencies
pdm install -G cli

# Install development dependencies
pdm install -dG dev -dG lint -dG test -dG docs

# Add new dependencies
pdm add <package>
pdm add -d <package>          # dev dependency
pdm add -dG test <package>    # test dependency
```

### Testing

```bash
# Run all tests with tox (tests Python 3.9-3.13)
tox

# Run specific Python version
tox -e python3.11

# Run pytest directly
pytest -v -s tests/base                    # Core tests
pytest -v -s tests/optional_imports         # CLI dependency tests
pytest -v -s tests/low_resources            # Memory-constrained tests
pytest -v -s tests/benchmark                # Performance tests

# Run single test
pytest -v -s tests/base/test_pbf_file_reader.py::test_name

# Run doctests
pytest -v -s --doctest-modules quackosm

# Run with coverage
coverage run --source=quackosm -m pytest tests/base
coverage report -m
coverage html  # Generate HTML report
```

### Code Quality

```bash
# Run all pre-commit hooks
pre-commit run --all-files

# Run specific hooks
pre-commit run ruff --all-files
pre-commit run mypy --all-files
pre-commit run docformatter --all-files

# Install pre-commit hooks (auto-installed via pdm post_install)
pre-commit install

# Ruff (linting and formatting)
ruff check quackosm --fix
ruff format quackosm

# Mypy (type checking - strict mode)
mypy quackosm

# Docformatter
docformatter --in-place --config pyproject.toml quackosm/**/*.py

# License checking (manual stage)
pre-commit run licensecheck --hook-stage manual
```

### Documentation

```bash
# Serve docs locally
mkdocs serve

# Build docs
mkdocs build

# Deploy docs (mike for versioning)
mike deploy --push --update-aliases 0.16.4 latest
```

### Version Bumping

```bash
# Bump version (uses bumpver)
bumpver update --patch
bumpver update --minor
bumpver update --major
```

## Architecture

### Core Processing Pipeline (32 Steps)

The PBF conversion follows a multi-stage pipeline orchestrated by `PbfFileReader`:

1. **Read nodes** from PBF (DuckDB's `ST_ReadOSM`)
2. **Filter nodes** - geometry intersection
3. **Filter nodes** - OSM tags
4. **Calculate distinct filtered node IDs**
5. **Read ways** from PBF
6. **Unnest ways** (expand node refs)
7. **Filter ways** - valid refs (join with filtered nodes)
8. **Filter ways** - geometry intersection
9. **Filter ways** - OSM tags
10. **Calculate distinct filtered way IDs**
11. **Read relations** from PBF
12. **Unnest relations** (expand way/node refs)
13. **Filter relations** - valid refs
14. **Filter relations** - geometry intersection
15. **Filter relations** - OSM tags
16. **Calculate distinct filtered relation IDs**
17. **Load required ways** (needed by relations)
18. **Calculate distinct required way IDs**
19. **Save filtered nodes** with Point geometries
20. **Group filtered ways** (chunked processing)
21. **Save filtered ways** with LineString/Polygon geometries
22. **Group required ways** (for relation reconstruction)
23. **Save required ways** with geometries
24. **Save filtered ways** with final geometries
25. **Save valid relation parts**
26. **Save relation inner parts** (holes)
27. **Save relation outer parts**
28. **Save relation outer parts with holes**
29. **Save relation outer parts without holes**
30. **Save filtered relations** with MultiPolygon geometries
31. **Save all features** (combine nodes, ways, relations)
32. **Save final GeoParquet file** (sorted by geometry)

### Key Components

#### PbfFileReader (pbf_file_reader.py:86)
Main orchestrator class:
- Configurable via `tags_filter`, `geometry_filter`, `osm_way_polygon_config`
- Three output methods: `convert_pbf_to_parquet()`, `convert_pbf_to_geodataframe()`, `convert_pbf_to_duckdb()`
- Implements intelligent caching with hash-based file naming
- Memory-aware chunking with `rows_per_group` auto-scaling

#### Convenience Functions (functions.py:1)
High-level wrappers:
- `convert_pbf_to_*` - Direct PBF conversion
- `convert_geometry_to_*` - Auto-download PBF for geometry
- `convert_osm_extract_to_*` - Query-based extract download

#### OSM Extracts System (osm_extracts/)
- `geofabrik.py`, `bbbike.py`, `osm_fr.py` - Extract source scrapers
- `extract.py` - Extract data model with IOU (Intersection over Union) matching
- `extracts_tree.py` - Spatial R-tree for finding best-matching extracts

#### Memory-Aware Processing
DuckDB operations are memory-intensive. QuackOSM handles this via:
- **Chunked processing**: `rows_per_group` ranges from 10K (< 1GB RAM) to 48M (> 32GB RAM)
- **Separate process**: Expensive queries run in `WorkerProcess` (from rq_geo_toolkit)
- **Graceful degradation**: Auto-reduces CPU cores if memory pressure detected

### File Naming Convention

Cached files use deterministic hash-based naming:
```
{pbf_name}_{tags_hash|nofilter}[_alltags]_{geom_hash|noclip}_{compact|exploded}[_ids_hash][_wkt].parquet
```

Examples:
- `monaco_nofilter_noclip_compact.parquet` - No filters
- `monaco_a9dd1c3c_noclip_exploded.parquet` - With tag filter
- `monaco_nofilter_430020b6_compact.parquet` - With geometry filter
- `monaco_a9dd1c3c_alltags_430020b6_compact.parquet` - Both filters, keep all tags

### DuckDB-Centric Design

All processing happens via DuckDB SQL queries:
- `ST_ReadOSM` for reading PBF primitives
- Heavy use of JOIN, GROUP BY, ORDER BY operations
- Parquet as intermediate format between steps
- Minimal Python-side processing (only geometry validation/fixing)

### Tag Filtering System

Two filter types (defined in `_osm_tags_filters.py:1`):
- `OsmTagsFilter`: Flat dict, e.g., `{"building": True, "amenity": ["restaurant", "cafe"]}`
- `GroupedOsmTagsFilter`: Categorized, e.g., `{"group1": {"building": True}, "group2": {"amenity": True}}`

Filter values:
- `True` - Include if tag key exists
- `False` - Exclude if tag key exists (negative filter)
- `["value1", "value2"]` - Include if tag key has specific values
- Merging logic handles conflicts and deduplication

### OSM Way Polygon Configuration

Defined in `osm_way_polygon_features.json`:
- Determines which OSM ways become Polygons vs LineStrings
- Based on tag keys and values (e.g., `building=*` → Polygon)
- Customizable via `osm_way_polygon_config` parameter

## Testing Philosophy

### Test Organization
- **Doctests**: Inline examples in docstrings (all modules)
- **Unit/Integration**: `tests/base/` (49,905 LOC - 6.3x ratio vs source)
- **GDAL Parity**: Validates geometry correctness using Hausdorff distance
- **Parametrized**: Extensive use of `@pytest.mark.parametrize` for combinations
- **Multi-version**: tox tests Python 3.9-3.13

### GDAL Validation
The `test_gdal_parity` function compares QuackOSM geometries against GDAL output:
- Uses Hausdorff distance for geometry comparison
- QuackOSM can sometimes fix geometries that GDAL loads with artifacts
- Critical for ensuring OSM geometry reconstruction correctness

### Coverage Requirements
- CI runs coverage for doctests, base tests, and optional imports
- Reports sent to Codecov
- Aim for high coverage but prioritize meaningful tests over coverage numbers

## Code Style

### Type Safety
- **Strict mypy**: All functions must have type hints
- **Runtime validation**: `typeguard` for runtime type checking
- **No implicit Optional**: Use `Optional[T]` explicitly

### Docstrings
- **Google style**: All public APIs must have docstrings
- **Examples**: Include doctest examples where applicable
- **Args/Returns**: Document all parameters and return values

### Linting
- **Ruff**: Enforces pycodestyle, pyflakes, pyupgrade, pydocstyle, isort, flake8-bugbear, etc.
- **Line length**: 100 characters
- **Target version**: Python 3.9+

### Commit Messages
- **Conventional commits**: Enforced via pre-commit hook
- Format: `type(scope): description`
- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## CI/CD Pipeline

### Development CI (ci-dev.yml)
Runs on PRs and pushes to `main`:
- pre-commit.ci hooks
- tox tests for Python 3.9-3.13
- Coverage reporting

### Production CI/CD (ci-prod.yml)
Runs on releases:
- Build package
- Run full test suite
- Publish to PyPI
- Generate and deploy versioned docs (mike)

### Pre-commit.ci
Automatically runs on PRs:
- Ruff (lint + format)
- Mypy type checking
- Docformatter
- Conventional commit validation

## Important Architectural Decisions

### 1. Memory-First Design
Always consider memory usage. DuckDB operations are memory-intensive, so:
- Use chunked processing for large datasets
- Test with `tests/low_resources/` for memory-constrained scenarios
- Monitor `rows_per_group` auto-scaling

### 2. DuckDB SQL Over Python
Prefer DuckDB SQL operations over Python:
- Faster execution
- Better memory management
- Leverages DuckDB's query optimizer

### 3. Caching is Critical
Hash-based caching prevents recomputation:
- Always check if cache hit is possible
- Use `ignore_cache=True` when testing new features
- File naming must reflect all parameters that affect output

### 4. Geometry Validation
OSM geometries aren't always perfect:
- Relations can have undefined topology
- Always validate and fix geometries using Shapely
- Test against GDAL output for parity

### 5. Progress Reporting
Three modes (via `_rich_progress.py:1`):
- **Transient** (default): Progress bars disappear after completion
- **Persistent**: Progress bars remain in terminal
- **Silent**: No output (for scripting)

## Common Development Patterns

### Adding a New OSM Extract Source
1. Create new file in `osm_extracts/` (e.g., `new_source.py`)
2. Implement `_get_new_source_index()` returning `GeoDataFrame`
3. Add to `OSM_EXTRACT_SOURCE_INDEX_FUNCTION` in `osm_extracts/__init__.py`
4. Add tests in `tests/base/test_osm_extracts.py`

### Adding New Tag Filter Logic
1. Modify `_osm_tags_filters.py`
2. Ensure merging logic handles new filter type
3. Add hash computation for caching
4. Add tests with parametrization

### Modifying the Processing Pipeline
1. Understand current 32-step pipeline (see Architecture section)
2. Identify which step to modify
3. Update `PbfFileReader` methods in `pbf_file_reader.py`
4. Test with Monaco PBF (small test file)
5. Run GDAL parity tests to ensure geometry correctness
6. Test memory usage with `tests/low_resources/`

## External Dependencies

### Core
- **DuckDB >= 1.1.2**: All PBF reading and SQL operations
- **PyArrow >= 16.0.0**: Parquet I/O
- **GeoPandas >= 0.6**: GeoDataFrame operations
- **Shapely >= 2**: Geometry validation/fixing
- **rq_geo_toolkit**: Multiprocessing utilities, GeoParquet compression/sorting

### Optional (CLI)
- **Typer**: CLI framework
- **s2sphere**: S2 index support

## Performance Considerations

### Disk Usage
Rule of thumb: 10x free space vs PBF file size (100MB PBF → 1GB free space)

### Multiprocessing
- Utilizes all available CPU cores by default
- Automatically reduces cores on memory pressure
- Use `WorkerProcess` for expensive queries

### Optimization Strategy
1. Profile with small PBF files first (Monaco)
2. Test with medium files (Estonia ~100MB)
3. Validate with large files (Poland ~2GB)
4. Always run `tests/benchmark/` after optimization changes

## Known Limitations

### WSL
DuckDB may try to use all available memory, which can conflict with Windows. Monitor memory usage.

### OSM Geometry Edge Cases
- Relations can have undefined topology
- Some geometries require post-processing fixes
- GDAL parity tests catch most issues

### Python 3.9 Support
Target version is Python 3.9+, so:
- No pattern matching (requires 3.10+)
- Use `Union[X, Y]` instead of `X | Y` type syntax
- Use `List[T]` instead of `list[T]` in public APIs (though `list[T]` is used internally)
