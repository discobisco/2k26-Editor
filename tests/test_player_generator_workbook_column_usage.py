from __future__ import annotations

import ast
import csv
import json
import sqlite3
import unittest
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_DIR = PROJECT_ROOT / "nba2k_editor" / "Player Generator"
MASTER_DB = GENERATOR_DIR / "NBA Player Data" / "NBA_DATA_Master.sqlite"
REPORT_DIR = PROJECT_ROOT / "test" / "artifacts"
REPORT_JSON = REPORT_DIR / "player_generator_workbook_column_usage.json"
REPORT_CSV = REPORT_DIR / "player_generator_workbook_column_usage.csv"

# Hardcoded snapshot of every sheet/header expected in NBA_DATA_Master.sqlite.
# The tests below compare this snapshot against the live SQL database, then scan
# the Player Generator Python files for usage of each table/header pair.
EXPECTED_WORKBOOK_TABLES: dict[str, str] = {'Team Abbrev': 'team_abbrev',
 'Team Stats Per 100 Pos': 'team_stats_per_100_pos',
 'Team Stats Per Game': 'team_stats_per_game',
 'Team Summaries': 'team_summaries',
 'Team Totals': 'team_totals',
 'Opponent Stats Per 100 Poss': 'opponent_stats_per_100_poss',
 'Opponent Stats Per Game': 'opponent_stats_per_game',
 'Opponent Totals': 'opponent_totals',
 'Draft Picks': 'draft_picks',
 'Player Season Info': 'player_season_info',
 'Player Info': 'player_info',
 'Player Per Game': 'player_per_game',
 'Player Per 36 min': 'player_per_36_min',
 'Player Per 100 Poss': 'player_per_100_poss',
 'Player Totals': 'player_totals',
 'Player Shooting': 'player_shooting',
 'Advanced': 'advanced',
 'Player Play by Play': 'player_play_by_play',
 'All Star Selections': 'all_star_selections',
 'All Teams': 'all_teams',
 'Player Award Shares': 'player_award_shares',
 'All team Voting': 'all_team_voting'}

EXPECTED_WORKBOOK_HEADERS: dict[str, list[str]] = {'Team Abbrev': ['season', 'lg', 'team', 'abbreviation', 'playoffs'],
 'Team Stats Per 100 Pos': ['season',
                            'lg',
                            'team',
                            'abbreviation',
                            'playoffs',
                            'g',
                            'mp',
                            'fg_per_100_poss',
                            'fga_per_100_poss',
                            'fg_percent',
                            'x3p_per_100_poss',
                            'x3pa_per_100_poss',
                            'x3p_percent',
                            'x2p_per_100_poss',
                            'x2pa_per_100_poss',
                            'x2p_percent',
                            'ft_per_100_poss',
                            'fta_per_100_poss',
                            'ft_percent',
                            'orb_per_100_poss',
                            'drb_per_100_poss',
                            'trb_per_100_poss',
                            'ast_per_100_poss',
                            'stl_per_100_poss',
                            'blk_per_100_poss',
                            'tov_per_100_poss',
                            'pf_per_100_poss',
                            'pts_per_100_poss'],
 'Team Stats Per Game': ['season',
                         'lg',
                         'team',
                         'abbreviation',
                         'playoffs',
                         'g',
                         'mp_per_game',
                         'fg_per_game',
                         'fga_per_game',
                         'fg_percent',
                         'x3p_per_game',
                         'x3pa_per_game',
                         'x3p_percent',
                         'x2p_per_game',
                         'x2pa_per_game',
                         'x2p_percent',
                         'ft_per_game',
                         'fta_per_game',
                         'ft_percent',
                         'orb_per_game',
                         'drb_per_game',
                         'trb_per_game',
                         'ast_per_game',
                         'stl_per_game',
                         'blk_per_game',
                         'tov_per_game',
                         'pf_per_game',
                         'pts_per_game'],
 'Team Summaries': ['season',
                    'lg',
                    'team',
                    'abbreviation',
                    'playoffs',
                    'age',
                    'w',
                    'l',
                    'pw',
                    'pl',
                    'mov',
                    'sos',
                    'srs',
                    'o_rtg',
                    'd_rtg',
                    'n_rtg',
                    'pace',
                    'f_tr',
                    'x3p_ar',
                    'ts_percent',
                    'e_fg_percent',
                    'tov_percent',
                    'orb_percent',
                    'ft_fga',
                    'opp_e_fg_percent',
                    'opp_tov_percent',
                    'drb_percent',
                    'opp_ft_fga',
                    'arena',
                    'attend',
                    'attend_g'],
 'Team Totals': ['season',
                 'lg',
                 'team',
                 'abbreviation',
                 'playoffs',
                 'g',
                 'mp',
                 'fg',
                 'fga',
                 'fg_percent',
                 'x3p',
                 'x3pa',
                 'x3p_percent',
                 'x2p',
                 'x2pa',
                 'x2p_percent',
                 'ft',
                 'fta',
                 'ft_percent',
                 'orb',
                 'drb',
                 'trb',
                 'ast',
                 'stl',
                 'blk',
                 'tov',
                 'pf',
                 'pts'],
 'Opponent Stats Per 100 Poss': ['season',
                                 'lg',
                                 'team',
                                 'abbreviation',
                                 'playoffs',
                                 'g',
                                 'mp',
                                 'opp_fg_per_100_poss',
                                 'opp_fga_per_100_poss',
                                 'opp_fg_percent',
                                 'opp_x3p_per_100_poss',
                                 'opp_x3pa_per_100_poss',
                                 'opp_x3p_percent',
                                 'opp_x2p_per_100_poss',
                                 'opp_x2pa_per_100_poss',
                                 'opp_x2p_percent',
                                 'opp_ft_per_100_poss',
                                 'opp_fta_per_100_poss',
                                 'opp_ft_percent',
                                 'opp_orb_per_100_poss',
                                 'opp_drb_per_100_poss',
                                 'opp_trb_per_100_poss',
                                 'opp_ast_per_100_poss',
                                 'opp_stl_per_100_poss',
                                 'opp_blk_per_100_poss',
                                 'opp_tov_per_100_poss',
                                 'opp_pf_per_100_poss',
                                 'opp_pts_per_100_poss'],
 'Opponent Stats Per Game': ['season',
                             'lg',
                             'team',
                             'abbreviation',
                             'playoffs',
                             'g',
                             'mp_per_game',
                             'opp_fg_per_game',
                             'opp_fga_per_game',
                             'opp_fg_percent',
                             'opp_x3p_per_game',
                             'opp_x3pa_per_game',
                             'opp_x3p_percent',
                             'opp_x2p_per_game',
                             'opp_x2pa_per_game',
                             'opp_x2p_percent',
                             'opp_ft_per_game',
                             'opp_fta_per_game',
                             'opp_ft_percent',
                             'opp_orb_per_game',
                             'opp_drb_per_game',
                             'opp_trb_per_game',
                             'opp_ast_per_game',
                             'opp_stl_per_game',
                             'opp_blk_per_game',
                             'opp_tov_per_game',
                             'opp_pf_per_game',
                             'opp_pts_per_game'],
 'Opponent Totals': ['season',
                     'lg',
                     'team',
                     'abbreviation',
                     'playoffs',
                     'g',
                     'mp',
                     'opp_fg',
                     'opp_fga',
                     'opp_fg_percent',
                     'opp_x3p',
                     'opp_x3pa',
                     'opp_x3p_percent',
                     'opp_x2p',
                     'opp_x2pa',
                     'opp_x2p_percent',
                     'opp_ft',
                     'opp_fta',
                     'opp_ft_percent',
                     'opp_orb',
                     'opp_drb',
                     'opp_trb',
                     'opp_ast',
                     'opp_stl',
                     'opp_blk',
                     'opp_tov',
                     'opp_pf',
                     'opp_pts'],
 'Draft Picks': ['season', 'lg', 'overall_pick', 'round', 'tm', 'player', 'player_id', 'college'],
 'Player Season Info': ['season', 'lg', 'player', 'player_id', 'age', 'team', 'pos', 'experience'],
 'Player Info': ['player',
                 'player_id',
                 'pos',
                 'ht_in_in',
                 'wt',
                 'birth_date',
                 'colleges',
                 'from',
                 'to',
                 'debut',
                 'hof'],
 'Player Per Game': ['season',
                     'lg',
                     'player',
                     'player_id',
                     'age',
                     'team',
                     'pos',
                     'g',
                     'gs',
                     'mp_per_game',
                     'fg_per_game',
                     'fga_per_game',
                     'fg_percent',
                     'x3p_per_game',
                     'x3pa_per_game',
                     'x3p_percent',
                     'x2p_per_game',
                     'x2pa_per_game',
                     'x2p_percent',
                     'e_fg_percent',
                     'ft_per_game',
                     'fta_per_game',
                     'ft_percent',
                     'orb_per_game',
                     'drb_per_game',
                     'trb_per_game',
                     'ast_per_game',
                     'stl_per_game',
                     'blk_per_game',
                     'tov_per_game',
                     'pf_per_game',
                     'pts_per_game'],
 'Player Per 36 min': ['season',
                       'lg',
                       'player',
                       'player_id',
                       'age',
                       'team',
                       'pos',
                       'g',
                       'gs',
                       'mp',
                       'fg_per_36_min',
                       'fga_per_36_min',
                       'fg_percent',
                       'x3p_per_36_min',
                       'x3pa_per_36_min',
                       'x3p_percent',
                       'x2p_per_36_min',
                       'x2pa_per_36_min',
                       'x2p_percent',
                       'e_fg_percent',
                       'ft_per_36_min',
                       'fta_per_36_min',
                       'ft_percent',
                       'orb_per_36_min',
                       'drb_per_36_min',
                       'trb_per_36_min',
                       'ast_per_36_min',
                       'stl_per_36_min',
                       'blk_per_36_min',
                       'tov_per_36_min',
                       'pf_per_36_min',
                       'pts_per_36_min'],
 'Player Per 100 Poss': ['season',
                         'lg',
                         'player',
                         'player_id',
                         'age',
                         'team',
                         'pos',
                         'g',
                         'gs',
                         'mp',
                         'fg_per_100_poss',
                         'fga_per_100_poss',
                         'fg_percent',
                         'x3p_per_100_poss',
                         'x3pa_per_100_poss',
                         'x3p_percent',
                         'x2p_per_100_poss',
                         'x2pa_per_100_poss',
                         'x2p_percent',
                         'e_fg_percent',
                         'ft_per_100_poss',
                         'fta_per_100_poss',
                         'ft_percent',
                         'orb_per_100_poss',
                         'drb_per_100_poss',
                         'trb_per_100_poss',
                         'ast_per_100_poss',
                         'stl_per_100_poss',
                         'blk_per_100_poss',
                         'tov_per_100_poss',
                         'pf_per_100_poss',
                         'pts_per_100_poss',
                         'o_rtg',
                         'd_rtg'],
 'Player Totals': ['season',
                   'lg',
                   'player',
                   'player_id',
                   'age',
                   'team',
                   'pos',
                   'g',
                   'gs',
                   'mp',
                   'fg',
                   'fga',
                   'fg_percent',
                   'x3p',
                   'x3pa',
                   'x3p_percent',
                   'x2p',
                   'x2pa',
                   'x2p_percent',
                   'e_fg_percent',
                   'ft',
                   'fta',
                   'ft_percent',
                   'orb',
                   'drb',
                   'trb',
                   'ast',
                   'stl',
                   'blk',
                   'tov',
                   'pf',
                   'pts',
                   'trp_dbl'],
 'Player Shooting': ['season',
                     'lg',
                     'player',
                     'player_id',
                     'age',
                     'team',
                     'pos',
                     'g',
                     'gs',
                     'mp',
                     'fg_percent',
                     'avg_dist_fga',
                     'percent_fga_from_x2p_range',
                     'percent_fga_from_x0_3_range',
                     'percent_fga_from_x3_10_range',
                     'percent_fga_from_x10_16_range',
                     'percent_fga_from_x16_3p_range',
                     'percent_fga_from_x3p_range',
                     'fg_percent_from_x2p_range',
                     'fg_percent_from_x0_3_range',
                     'fg_percent_from_x3_10_range',
                     'fg_percent_from_x10_16_range',
                     'fg_percent_from_x16_3p_range',
                     'fg_percent_from_x3p_range',
                     'percent_assisted_x2p_fg',
                     'percent_assisted_x3p_fg',
                     'percent_dunks_of_fga',
                     'num_of_dunks',
                     'percent_corner_3s_of_3pa',
                     'corner_3_point_percent',
                     'num_heaves_attempted',
                     'num_heaves_made'],
 'Advanced': ['season',
              'lg',
              'player',
              'player_id',
              'age',
              'team',
              'pos',
              'g',
              'gs',
              'mp',
              'per',
              'ts_percent',
              'x3p_ar',
              'f_tr',
              'orb_percent',
              'drb_percent',
              'trb_percent',
              'ast_percent',
              'stl_percent',
              'blk_percent',
              'tov_percent',
              'usg_percent',
              'ows',
              'dws',
              'ws',
              'ws_48',
              'obpm',
              'dbpm',
              'bpm',
              'vorp'],
 'Player Play by Play': ['season',
                         'lg',
                         'player',
                         'player_id',
                         'age',
                         'team',
                         'pos',
                         'g',
                         'gs',
                         'mp',
                         'pg_percent',
                         'sg_percent',
                         'sf_percent',
                         'pf_percent',
                         'c_percent',
                         'on_court_plus_minus_per_100_poss',
                         'net_plus_minus_per_100_poss',
                         'bad_pass_turnover',
                         'lost_ball_turnover',
                         'shooting_foul_committed',
                         'offensive_foul_committed',
                         'shooting_foul_drawn',
                         'offensive_foul_drawn',
                         'points_generated_by_assists',
                         'and1',
                         'fga_blocked'],
 'All Star Selections': ['player', 'player_id', 'team', 'season', 'lg', 'replaced'],
 'All Teams': ['season', 'lg', 'type', 'number_tm', 'player', 'player_id', 'position'],
 'Player Award Shares': ['season',
                         'award',
                         'player',
                         'player_id',
                         'age',
                         'first',
                         'pts_won',
                         'pts_max',
                         'share',
                         'winner'],
 'All team Voting': ['season',
                     'lg',
                     'type',
                     'number_tm',
                     'position',
                     'player',
                     'player_id',
                     'age',
                     'pts_won',
                     'pts_max',
                     'share',
                     'x1st_tm',
                     'x2nd_tm',
                     'x3rd_tm']}

# Tables that become first-class PlayerEvidence attributes in player_evidence.py.
# This lets the scanner distinguish table-specific usage such as:
#   _number(evidence.per_game, "pts_per_game") -> player_per_game.pts_per_game
EVIDENCE_ATTR_TO_TABLE = {
    "identity": "player_info",
    "season_info": "player_season_info",
    "per_game": "player_per_game",
    "totals": "player_totals",
    "per_36": "player_per_36_min",
    "per_100": "player_per_100_poss",
    "advanced": "advanced",
    "shooting": "player_shooting",
    "play_by_play": "player_play_by_play",
    "team_stats_per_game": "team_stats_per_game",
    "team_stats_per_100": "team_stats_per_100_pos",
    "team_summary": "team_summaries",
    "opponent_stats_per_game": "opponent_stats_per_game",
    "opponent_stats_per_100": "opponent_stats_per_100_poss",
}

# Static scan target: the generator runtime code, not docs or bytecode.
GENERATOR_SOURCE_FILES = tuple(
    path
    for path in sorted(GENERATOR_DIR.glob("*.py"))
    if path.name != "__init__.py"
)


@dataclass(frozen=True)
class WorkbookColumn:
    sheet_name: str
    table_name: str
    column_name: str
    declared_type: str
    ordinal: int
    numeric: bool

    @property
    def key(self) -> tuple[str, str]:
        return (self.table_name, self.column_name)


@dataclass
class UsageHit:
    table_name: str | None
    column_name: str
    usage_type: str
    file: str
    line: int
    function: str
    source: str


@dataclass
class ColumnUsageReportRow:
    sheet_name: str
    table_name: str
    column_name: str
    declared_type: str
    ordinal: int
    numeric: bool
    used: bool
    usage_count: int
    ambiguous_literal_count: int
    used_for: list[str] = field(default_factory=list)
    ambiguous_literals: list[str] = field(default_factory=list)


def load_database_workbook_tables_and_headers() -> tuple[dict[str, str], dict[str, list[str]]]:
    if not MASTER_DB.is_file():
        raise FileNotFoundError(f"missing master SQLite DB: {MASTER_DB}")

    tables_by_sheet: dict[str, str] = {}
    headers_by_sheet: dict[str, list[str]] = {}
    with sqlite3.connect(MASTER_DB) as connection:
        connection.row_factory = sqlite3.Row
        tables = connection.execute(
            "SELECT sheet_name, table_name FROM workbook_tables ORDER BY ordinal"
        ).fetchall()
        for table in tables:
            sheet_name = str(table["sheet_name"])
            table_name = str(table["table_name"])
            tables_by_sheet[sheet_name] = table_name
            headers_by_sheet[sheet_name] = [
                str(col["name"])
                for col in connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
            ]
    return tables_by_sheet, headers_by_sheet


def load_workbook_columns() -> list[WorkbookColumn]:
    if not MASTER_DB.is_file():
        raise FileNotFoundError(f"missing master SQLite DB: {MASTER_DB}")

    columns: list[WorkbookColumn] = []
    with sqlite3.connect(MASTER_DB) as connection:
        connection.row_factory = sqlite3.Row
        for sheet_name, table_name in EXPECTED_WORKBOOK_TABLES.items():
            live_columns = {
                str(col["name"]): col
                for col in connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
            }
            for ordinal, column_name in enumerate(EXPECTED_WORKBOOK_HEADERS[sheet_name]):
                col = live_columns[column_name]
                declared_type = str(col["type"] or "")
                columns.append(
                    WorkbookColumn(
                        sheet_name=sheet_name,
                        table_name=table_name,
                        column_name=column_name,
                        declared_type=declared_type,
                        ordinal=ordinal,
                        numeric=is_numeric_sql_type(declared_type),
                    )
                )
    return columns


def is_numeric_sql_type(declared_type: str) -> bool:
    normalized = declared_type.upper()
    return any(token in normalized for token in ("INT", "REAL", "NUM", "FLOAT", "DOUBLE", "DECIMAL"))


def build_prefix_aliases(columns: list[WorkbookColumn]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for col in columns:
        aliases[col.table_name] = col.table_name
        aliases[col.sheet_name.lower().replace(" ", "_")] = col.table_name
    for attr, table_name in EVIDENCE_ATTR_TO_TABLE.items():
        aliases[attr] = table_name
    return aliases


class GeneratorUsageScanner(ast.NodeVisitor):
    def __init__(self, path: Path, columns: list[WorkbookColumn], prefix_aliases: dict[str, str]) -> None:
        self.path = path
        self.relative_path = path.relative_to(PROJECT_ROOT).as_posix()
        self.source_text = path.read_text(encoding="utf-8")
        self.source_lines = self.source_text.splitlines()
        self.columns_by_name: dict[str, list[WorkbookColumn]] = {}
        self.columns_by_key = {column.key: column for column in columns}
        for column in columns:
            self.columns_by_name.setdefault(column.column_name, []).append(column)
        self.prefix_aliases = prefix_aliases
        self.hits: list[UsageHit] = []
        self.function_stack: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, str):
            self._record_string_literal(node, node.value)
        self.generic_visit(node)

    def _record_string_literal(self, node: ast.Constant, value: str) -> None:
        if not value:
            return

        # Qualified references like "per_game.pts_per_game" are audit metadata,
        # not proof that a formula actually reads the workbook column. Count them
        # only when they are a literal argument to an evidence.source_context
        # accessor. A catch-all tuple of qualified strings must not satisfy this
        # test.
        qualified = self._qualified_reference(value)
        if qualified is not None:
            table_name, column_name = qualified
            if self._source_context_literal_arg(node) and (table_name, column_name) in self.columns_by_key:
                self.hits.append(self._hit(node, table_name, column_name, "source_context_accessor"))
            return

        # Evidence accessors: _number(evidence.per_game, "pts_per_game") or
        # evidence.per_game.get("pts_per_game"). These are table-specific.
        evidence_table = self._evidence_table_for_literal_arg(node)
        if evidence_table and (evidence_table, value) in self.columns_by_key:
            self.hits.append(self._hit(node, evidence_table, value, "evidence_accessor"))
            return

        # Bare column string. Record separately because duplicated/generic names
        # like season, age, g, team, player_id cannot prove sheet-specific usage.
        if value in self.columns_by_name:
            self.hits.append(self._hit(node, None, value, "ambiguous_literal"))

    def _qualified_reference(self, value: str) -> tuple[str, str] | None:
        """Resolve literals like player_totals.pts or sparse_era.player_totals.pts."""
        if "." not in value:
            return None
        parts = value.split(".")
        column_name = parts[-1]
        for start in range(len(parts) - 1):
            prefix = ".".join(parts[start:-1])
            table_name = self.prefix_aliases.get(prefix)
            if table_name is not None:
                return table_name, column_name
        return None

    def _evidence_table_for_literal_arg(self, node: ast.Constant) -> str | None:
        parent = getattr(node, "parent", None)
        if not isinstance(parent, ast.Call):
            return None

        # _number(evidence.per_game, "pts_per_game")
        for arg in parent.args:
            table_name = self._table_from_evidence_attribute(arg)
            if table_name:
                return table_name

        # evidence.per_game.get("pts_per_game")
        if isinstance(parent.func, ast.Attribute) and parent.func.attr == "get":
            return self._table_from_evidence_attribute(parent.func.value)

        return None

    def _source_context_literal_arg(self, node: ast.Constant) -> bool:
        parent = getattr(node, "parent", None)
        if not isinstance(parent, ast.Call):
            return False

        # _number(evidence.source_context, "team_totals.pts")
        for arg in parent.args:
            if self._is_evidence_source_context(arg):
                return True

        # evidence.source_context.get("team_totals.pts")
        return (
            isinstance(parent.func, ast.Attribute)
            and parent.func.attr == "get"
            and self._is_evidence_source_context(parent.func.value)
        )

    def _is_evidence_source_context(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "source_context"
            and isinstance(node.value, ast.Name)
            and node.value.id == "evidence"
        )

    def _table_from_evidence_attribute(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "evidence":
            return EVIDENCE_ATTR_TO_TABLE.get(node.attr)
        return None

    def _hit(self, node: ast.AST, table_name: str | None, column_name: str, usage_type: str) -> UsageHit:
        line = int(getattr(node, "lineno", 0) or 0)
        source = self.source_lines[line - 1].strip() if 1 <= line <= len(self.source_lines) else ""
        return UsageHit(
            table_name=table_name,
            column_name=column_name,
            usage_type=usage_type,
            file=self.relative_path,
            line=line,
            function=self.function_stack[-1] if self.function_stack else "<module>",
            source=source,
        )


def add_parent_links(tree: ast.AST) -> None:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            setattr(child, "parent", parent)


def scan_generator_usage(columns: list[WorkbookColumn]) -> tuple[list[UsageHit], list[UsageHit]]:
    prefix_aliases = build_prefix_aliases(columns)
    specific_hits: list[UsageHit] = []
    ambiguous_hits: list[UsageHit] = []
    for path in GENERATOR_SOURCE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        add_parent_links(tree)
        scanner = GeneratorUsageScanner(path, columns, prefix_aliases)
        scanner.visit(tree)
        for hit in scanner.hits:
            if hit.table_name is None:
                ambiguous_hits.append(hit)
            else:
                specific_hits.append(hit)
    return specific_hits, ambiguous_hits


def build_usage_report() -> list[ColumnUsageReportRow]:
    columns = load_workbook_columns()
    specific_hits, ambiguous_hits = scan_generator_usage(columns)

    specific_by_key: dict[tuple[str, str], list[UsageHit]] = {}
    ambiguous_by_column: dict[str, list[UsageHit]] = {}
    for hit in specific_hits:
        assert hit.table_name is not None
        specific_by_key.setdefault((hit.table_name, hit.column_name), []).append(hit)
    for hit in ambiguous_hits:
        ambiguous_by_column.setdefault(hit.column_name, []).append(hit)

    rows: list[ColumnUsageReportRow] = []
    for column in columns:
        usage_hits = specific_by_key.get(column.key, [])
        ambiguous = ambiguous_by_column.get(column.column_name, [])
        rows.append(
            ColumnUsageReportRow(
                sheet_name=column.sheet_name,
                table_name=column.table_name,
                column_name=column.column_name,
                declared_type=column.declared_type,
                ordinal=column.ordinal,
                numeric=column.numeric,
                used=bool(usage_hits),
                usage_count=len(usage_hits),
                ambiguous_literal_count=len(ambiguous),
                used_for=[format_hit(hit) for hit in usage_hits],
                ambiguous_literals=[format_hit(hit) for hit in ambiguous],
            )
        )
    return rows


def format_hit(hit: UsageHit) -> str:
    return f"{hit.usage_type}:{hit.function}@{hit.file}:{hit.line}: {hit.source}"


def write_usage_report(rows: list[ColumnUsageReportRow]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(
        json.dumps([asdict(row) for row in rows], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    with REPORT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "sheet_name",
                "table_name",
                "column_name",
                "declared_type",
                "ordinal",
                "numeric",
                "used",
                "usage_count",
                "ambiguous_literal_count",
                "used_for",
                "ambiguous_literals",
            ),
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "sheet_name": row.sheet_name,
                    "table_name": row.table_name,
                    "column_name": row.column_name,
                    "declared_type": row.declared_type,
                    "ordinal": row.ordinal,
                    "numeric": row.numeric,
                    "used": row.used,
                    "usage_count": row.usage_count,
                    "ambiguous_literal_count": row.ambiguous_literal_count,
                    "used_for": " | ".join(row.used_for),
                    "ambiguous_literals": " | ".join(row.ambiguous_literals),
                }
            )


class TestPlayerGeneratorWorkbookColumnUsage(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = build_usage_report()
        write_usage_report(cls.rows)

    def test_qualified_literal_catch_all_does_not_count_as_usage(self) -> None:
        columns = load_workbook_columns()
        source: str = '''
_WORKBOOK_NUMERIC_FORMULA_INPUTS = ("team_totals.pts", "advanced.ws")

def fake_coverage(evidence):
    source = evidence.source_context or {}
    for key in _WORKBOOK_NUMERIC_FORMULA_INPUTS:
        source.get(key)
    return {"workbook_numeric_context": (0.5, _WORKBOOK_NUMERIC_FORMULA_INPUTS)}
'''
        tree = ast.parse(source)
        add_parent_links(tree)
        scanner = GeneratorUsageScanner(
            GENERATOR_DIR / "player_rules.py",
            columns,
            build_prefix_aliases(columns),
        )
        scanner.source_text = source
        scanner.source_lines = [str(line) for line in source.splitlines()]
        scanner.hits.clear()
        scanner.visit(tree)
        specific_hits = [hit for hit in scanner.hits if hit.table_name is not None]
        self.assertEqual([], specific_hits)

    def test_source_context_literal_accessor_counts_as_usage(self) -> None:
        columns = load_workbook_columns()
        source: str = '''
def real_source_context_formula(evidence):
    return _number(evidence.source_context, "team_totals.pts")
'''
        tree = ast.parse(source)
        add_parent_links(tree)
        scanner = GeneratorUsageScanner(
            GENERATOR_DIR / "player_rules.py",
            columns,
            build_prefix_aliases(columns),
        )
        scanner.source_text = source
        scanner.source_lines = [str(line) for line in source.splitlines()]
        scanner.hits.clear()
        scanner.visit(tree)
        self.assertEqual(
            [("team_totals", "pts", "source_context_accessor")],
            [(hit.table_name, hit.column_name, hit.usage_type) for hit in scanner.hits if hit.table_name is not None],
        )

    def test_evidence_accessor_counts_as_usage(self) -> None:
        columns = load_workbook_columns()
        source: str = '''
def real_formula(evidence):
    return _number(evidence.totals, "pts")
'''
        tree = ast.parse(source)
        add_parent_links(tree)
        scanner = GeneratorUsageScanner(
            GENERATOR_DIR / "player_rules.py",
            columns,
            build_prefix_aliases(columns),
        )
        scanner.source_text = source
        scanner.source_lines = [str(line) for line in source.splitlines()]
        scanner.hits.clear()
        scanner.visit(tree)
        self.assertEqual(
            [("player_totals", "pts")],
            [(hit.table_name, hit.column_name) for hit in scanner.hits if hit.table_name is not None],
        )

    def test_numeric_workbook_usage_report_keeps_unused_columns_visible(self) -> None:
        numeric_rows = [row for row in self.rows if row.numeric]
        used_numeric_rows = [row for row in numeric_rows if row.usage_count > 0]
        unused_numeric_rows = [row for row in numeric_rows if row.usage_count == 0]
        self.assertGreater(len(used_numeric_rows), 0)
        self.assertGreater(len(unused_numeric_rows), 0)

    def test_usage_report_artifacts_are_written(self) -> None:
        self.assertTrue(REPORT_JSON.is_file(), REPORT_JSON)
        self.assertTrue(REPORT_CSV.is_file(), REPORT_CSV)
        self.assertGreater(REPORT_JSON.stat().st_size, 0)
        self.assertGreater(REPORT_CSV.stat().st_size, 0)


if __name__ == "__main__":
    rows = build_usage_report()
    write_usage_report(rows)
    total = len(rows)
    used = sum(1 for row in rows if row.used)
    numeric_total = sum(1 for row in rows if row.numeric)
    numeric_used = sum(1 for row in rows if row.numeric and row.used)
    print(f"wrote {REPORT_JSON}")
    print(f"wrote {REPORT_CSV}")
    print(f"columns used: {used}/{total}")
    print(f"numeric columns used: {numeric_used}/{numeric_total}")
    unittest.main(argv=[__file__])
