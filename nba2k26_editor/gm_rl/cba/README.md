# gm_rl/cba folder

## Responsibilities
- CBA extraction, schema, normalization, and repository logic.
- Owns direct Python files: `__init__.py`, `docx_reader.py`, `extractors.py`, `normalizer.py`, `repository.py`, `schema.py`, `section_registry.py`.
- Maintains folder-local runtime behavior and boundaries used by the editor.

## Technical Deep Dive
CBA extraction, schema, normalization, and repository logic.
This folder currently has 7 direct Python modules. Function-tree coverage below is exhaustive for direct files and includes nested callables.

## Runtime/Data Flow
1. Callers enter this folder through public entry modules or imported helper functions.
2. Folder code performs domain-specific orchestration and delegates to adjacent layers as needed.
3. Results/events/state are returned to UI, model, runtime, or CLI callers depending on workflow.

## Integration Points
- Extractor CLI in `nba2k_editor/entrypoints/extract_cba_rules.py` drives this folder.
- AI/RL legality logic consumes emitted artifacts.

## Function Tree
### `__init__.py`
- No callable definitions.

### `docx_reader.py`
  - [def] docx_reader.py::DocxContent.paragraph
  - [def] docx_reader.py::DocxContent.paragraphs_slice
  - [def] docx_reader.py::DocxContent.table
- [def] docx_reader.py::_norm_text
- [def] docx_reader.py::load_docx
- [def] docx_reader.py::find_paragraph
- [def] docx_reader.py::find_all_paragraphs
- [def] docx_reader.py::parse_percent
- [def] docx_reader.py::parse_int
- [def] docx_reader.py::parse_currency_amount
- [def] docx_reader.py::extract_date_token
- [def] docx_reader.py::table_data_rows

### `extractors.py`
- [def] extractors.py::_now_utc
- [def] extractors.py::_load_yaml_json
- [def] extractors.py::load_manifest
- [def] extractors.py::load_manual_overrides
- [def] extractors.py::_add_citation
- [def] extractors.py::_parse_money_rate
- [def] extractors.py::_extract_cap_rules
  - [def] extractors.py::_extract_cap_rules._parse_tax_table
- [def] extractors.py::_extract_contract_rules
- [def] extractors.py::_extract_trade_rules
- [def] extractors.py::_extract_draft_rules
- [def] extractors.py::_extract_free_agency_rules
- [def] extractors.py::_extract_roster_rules
- [def] extractors.py::extract_raw_rules

### `normalizer.py`
- [def] normalizer.py::_get_nested
- [def] normalizer.py::_set_nested
- [def] normalizer.py::_apply_overrides
- [def] normalizer.py::_validate_required_fields
- [def] normalizer.py::_find_unresolved_fields
  - [def] normalizer.py::_find_unresolved_fields.walk
- [def] normalizer.py::normalize_rules
- [def] normalizer.py::ruleset_to_all_years_payload

### `repository.py`
- [def] repository.py::_cba_dir
- [def] repository.py::default_ruleset_path
- [def] repository.py::load_ruleset
- [def] repository.py::load_ruleset_for_season

### `schema.py`
  - [def] schema.py::CbaRuleSet.to_dict
  - [def] schema.py::CbaRuleSet.from_dict

### `section_registry.py`
- No callable definitions.

## Failure Modes and Debugging
- Upstream schema or dependency drift can surface runtime failures in this layer.
- Environment mismatches (platform, optional deps, file paths) can reduce or disable functionality.
- Nested call paths are easiest to diagnose by following this README function tree and runtime logs.

## Test Coverage Notes
- Coverage for this folder is provided by related suites under `nba2k_editor/tests`.
- Use targeted pytest runs around impacted modules after edits.
