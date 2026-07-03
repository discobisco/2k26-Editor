from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TeamSnapshot:
    team_id: str
    index: int
    address: int
    label: str
    city: str | None = None
    name: str | None = None
    wins: int | None = None
    losses: int | None = None
    conference_rank: int | None = None
    division_rank: int | None = None
    playoff_seed: int | None = None
    payroll: int | None = None
    cap_room: int | None = None
    data_sources: tuple[str, ...] = ("Existing editor cache",)

    @property
    def display_name(self) -> str:
        parts = [part for part in (self.city, self.name) if part]
        return " ".join(parts) if parts else self.label

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlayerSnapshot:
    player_id: str
    index: int
    address: int
    label: str
    team_id: str | None
    roster_slot: int | None = None
    roster_slot_field: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    overall: int | None = None
    potential: int | None = None
    position: str | None = None
    age: int | None = None
    data_sources: tuple[str, ...] = ("Existing editor cache",)

    @property
    def display_name(self) -> str:
        parts = [part for part in (self.first_name, self.last_name) if part]
        return " ".join(parts) if parts else self.label

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveFranchiseSnapshot:
    teams: tuple[TeamSnapshot, ...] = ()
    roster_players: tuple[PlayerSnapshot, ...] = ()
    full_app_dataset: dict[str, Any] = field(default_factory=dict)
    data_sources: tuple[str, ...] = ("Existing editor model dataset",)

    def to_dict(self) -> dict[str, Any]:
        return {
            "teams": [team.to_dict() for team in self.teams],
            "roster_players": [player.to_dict() for player in self.roster_players],
            "full_app_dataset": dict(self.full_app_dataset),
            "data_sources": list(self.data_sources),
        }


@dataclass(frozen=True)
class FrontOfficeProfile:
    team_id: str
    role: str
    profile: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SimRequest:
    team_id: str
    request: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LeagueSimPlan:
    plan: dict[str, Any] = field(default_factory=dict)
    team_requests: tuple[SimRequest, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": dict(self.plan),
            "team_requests": [request.to_dict() for request in self.team_requests],
        }


@dataclass(frozen=True)
class FranchiseLLMResult:
    panel_reports: dict[str, str] = field(default_factory=dict)
    front_offices: tuple[FrontOfficeProfile, ...] = ()
    sim_plan: LeagueSimPlan = field(default_factory=LeagueSimPlan)
    trade_proposals: tuple[dict[str, Any], ...] = ()
    signing_plans: tuple[dict[str, Any], ...] = ()
    draft_actions: tuple[dict[str, Any], ...] = ()
    roster_moves: tuple[dict[str, Any], ...] = ()
    trade_deadline: dict[str, Any] = field(default_factory=dict)
    offseason_phases: tuple[dict[str, Any], ...] = ()
    league_meetings: tuple[dict[str, Any], ...] = ()
    rule_votes: tuple[dict[str, Any], ...] = ()
    staff_decisions: tuple[dict[str, Any], ...] = ()
    scouting: dict[str, Any] = field(default_factory=dict)
    expansion_draft: dict[str, Any] = field(default_factory=dict)
    draft: dict[str, Any] = field(default_factory=dict)
    free_agency: dict[str, Any] = field(default_factory=dict)
    consequences: tuple[dict[str, Any], ...] = ()
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "panel_reports": dict(self.panel_reports),
            "front_offices": [profile.to_dict() for profile in self.front_offices],
            "sim_plan": self.sim_plan.to_dict(),
            "trade_proposals": [dict(proposal) for proposal in self.trade_proposals],
            "signing_plans": [dict(plan) for plan in self.signing_plans],
            "draft_actions": [dict(action) for action in self.draft_actions],
            "roster_moves": [dict(move) for move in self.roster_moves],
            "trade_deadline": dict(self.trade_deadline),
            "offseason_phases": [dict(phase) for phase in self.offseason_phases],
            "league_meetings": [dict(meeting) for meeting in self.league_meetings],
            "rule_votes": [dict(vote) for vote in self.rule_votes],
            "staff_decisions": [dict(decision) for decision in self.staff_decisions],
            "scouting": dict(self.scouting),
            "expansion_draft": dict(self.expansion_draft),
            "draft": dict(self.draft),
            "free_agency": dict(self.free_agency),
            "consequences": [dict(consequence) for consequence in self.consequences],
            "raw_output": self.raw_output,
        }


@dataclass(frozen=True)
class FranchiseDashboard:
    snapshot: LiveFranchiseSnapshot
    llm_result: FranchiseLLMResult
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def sim_plan(self) -> LeagueSimPlan:
        return self.llm_result.sim_plan

    @property
    def front_office_messages(self) -> tuple[str, ...]:
        inbox = self.llm_result.panel_reports.get("Front Office Inbox", "")
        return (inbox,) if inbox else ()

    @property
    def panel_reports(self) -> dict[str, str]:
        return self.llm_result.panel_reports

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot": self.snapshot.to_dict(),
            "llm_result": self.llm_result.to_dict(),
            "sim_plan": self.sim_plan.to_dict(),
            "front_office_messages": list(self.front_office_messages),
            "panel_reports": dict(self.panel_reports),
            "metadata": dict(self.metadata),
        }
