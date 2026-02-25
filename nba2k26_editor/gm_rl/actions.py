from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import torch

from nba2k_editor.gm_rl.adapters.base import PlayerState, RosterState
from nba2k_editor.gm_rl.cba.schema import CbaRuleSet

# --------------------------------------------------------------------------- #
# Action spaces and masks
# --------------------------------------------------------------------------- #


@dataclass
class ActionSpaceSpec:
    draft_slots: int = 30
    trade_candidates: int = 64
    rotation_templates: int = 6
    contract_candidates: int = 32
    roster_moves: int = 6

    @property
    def sizes(self) -> List[int]:
        return [
            self.draft_slots,
            self.trade_candidates,
            self.rotation_templates,
            self.contract_candidates,
            self.roster_moves,
        ]


@dataclass
class ActionMask:
    draft: torch.Tensor
    trade: torch.Tensor
    rotation: torch.Tensor
    contract: torch.Tensor
    roster_move: torch.Tensor

    def to(self, device: torch.device) -> "ActionMask":
        return ActionMask(
            draft=self.draft.to(device),
            trade=self.trade.to(device),
            rotation=self.rotation.to(device),
            contract=self.contract.to(device),
            roster_move=self.roster_move.to(device),
        )


@dataclass
class GMTransaction:
    head: str
    payload: Dict
    repaired: bool = False
    reasons: List[str] = field(default_factory=list)


class ActionMaskBuilder:
    """Compute legality masks from roster state."""

    def __init__(self, spec: ActionSpaceSpec, cba_rules: CbaRuleSet | None = None) -> None:
        self.spec = spec
        self.cba_rules = cba_rules
        self.last_cba_block_reasons: List[str] = []
        self.last_cba_warn_reasons: List[str] = []
        self.last_cba_citation_ids: List[str] = []

    def _record_block(self, code: str, citation_ids: List[str]) -> None:
        if code not in self.last_cba_block_reasons:
            self.last_cba_block_reasons.append(code)
        for cid in citation_ids:
            if cid not in self.last_cba_citation_ids:
                self.last_cba_citation_ids.append(cid)

    def _record_warn(self, code: str, citation_ids: List[str]) -> None:
        if code not in self.last_cba_warn_reasons:
            self.last_cba_warn_reasons.append(code)
        for cid in citation_ids:
            if cid not in self.last_cba_citation_ids:
                self.last_cba_citation_ids.append(cid)

    @staticmethod
    def _citation_ids(rule_citations: Dict[str, List[str]], key: str) -> List[str]:
        return list(rule_citations.get(key, []))

    def build(self, state: RosterState, team_id: int) -> ActionMask:
        self.last_cba_block_reasons = []
        self.last_cba_warn_reasons = []
        self.last_cba_citation_ids = []
        team = state.get_team(team_id)
        ctx = state.context
        mask_draft = torch.ones(self.spec.draft_slots, dtype=torch.bool)
        if team.roster_size() >= ctx.maximum_roster:
            mask_draft[:] = False

        all_players = sorted(state.players.values(), key=lambda p: p.player_id)
        trade_pool = [p for p in all_players if p.team_id != team_id]
        trade_mask = torch.zeros(self.spec.trade_candidates, dtype=torch.bool)
        for i, p in enumerate(trade_pool[: self.spec.trade_candidates]):
            trade_mask[i] = True

        rotation_mask = torch.ones(self.spec.rotation_templates, dtype=torch.bool)

        contract_candidates = sorted(team.roster, key=lambda pid: state.players[pid].minutes_per_game, reverse=True)
        contract_mask = torch.zeros(self.spec.contract_candidates, dtype=torch.bool)
        for i, pid in enumerate(contract_candidates[: self.spec.contract_candidates]):
            player = state.players[pid]
            contract_mask[i] = player.contract.years_left <= 3

        roster_mask = torch.ones(self.spec.roster_moves, dtype=torch.bool)
        if team.roster_size() <= ctx.minimum_roster:
            roster_mask[1:] = False  # disallow waives when at minimum

        # CBA hard constraints + soft warnings
        if self.cba_rules:
            trade_citations = self._citation_ids(self.cba_rules.trade.citations, "post_deadline_trade_blocked")
            apron_citations = self._citation_ids(self.cba_rules.cap.citations, "transaction_restrictions")
            contract_citations = self._citation_ids(self.cba_rules.contract.citations, "max_salary_percent_by_service")
            roster_citations = self._citation_ids(self.cba_rules.roster.citations, "regular_season_roster_bounds")
            wait_citations = self._citation_ids(self.cba_rules.trade.citations, "trade_wait_windows")

            if ctx.current_week >= ctx.trade_deadline_week:
                trade_mask[:] = False
                self._record_block("cba_blocked_trade_deadline", trade_citations)

            second_apron = max(float(ctx.second_apron_level or 0.0), float(ctx.hard_cap or 0.0))
            if second_apron > 0.0 and float(team.payroll) > second_apron:
                trade_mask[:] = False
                self._record_block("cba_blocked_second_apron_trade_restriction", apron_citations)

            if float(ctx.hard_cap or 0.0) > 0.0 and float(team.payroll) >= float(ctx.hard_cap):
                contract_mask[:] = False
                if roster_mask.numel() > 2:
                    roster_mask[2] = False  # block sign operation when cap-constrained
                self._record_block("cba_blocked_hard_cap_contract", contract_citations)

            if team.roster_size() >= self.cba_rules.roster.regular_season_max_players:
                mask_draft[:] = False
                if roster_mask.numel() > 2:
                    roster_mask[2] = False
                self._record_block("cba_blocked_roster_limit", roster_citations)

            # Current state snapshot lacks per-player contract-sign timestamps, so this remains advisory.
            self._record_warn("cba_warn_trade_wait_windows_unchecked", wait_citations)

        return ActionMask(
            draft=mask_draft,
            trade=trade_mask,
            rotation=rotation_mask,
            contract=contract_mask,
            roster_move=roster_mask,
        )


# --------------------------------------------------------------------------- #
# Grammar / legalizer
# --------------------------------------------------------------------------- #


class ActionGrammar:
    """Turn discrete head outputs into valid GMTransaction objects."""

    def __init__(self, spec: ActionSpaceSpec, repair_illegal: bool = False, cba_rules: CbaRuleSet | None = None) -> None:
        self.spec = spec
        self.repair_illegal = repair_illegal
        self.cba_rules = cba_rules
        self.last_cba_block_reasons: List[str] = []
        self.last_cba_warn_reasons: List[str] = []
        self.last_cba_citation_ids: List[str] = []

    def decode(self, head_indices: Tuple[int, int, int, int, int], state: RosterState, team_id: int) -> GMTransaction:
        draft_idx, trade_idx, rotation_idx, contract_idx, roster_idx = head_indices
        mask_builder = ActionMaskBuilder(self.spec, cba_rules=self.cba_rules)
        masks = mask_builder.build(state, team_id)
        self.last_cba_block_reasons = list(mask_builder.last_cba_block_reasons)
        self.last_cba_warn_reasons = list(mask_builder.last_cba_warn_reasons)
        self.last_cba_citation_ids = list(mask_builder.last_cba_citation_ids)
        # Draft
        if not masks.draft[min(draft_idx, self.spec.draft_slots - 1)]:
            if self.repair_illegal:
                draft_idx = self._first_true_index(masks.draft, default=0)
            else:
                return GMTransaction(head="draft", payload={"team_id": team_id, "draft_slot": -1}, repaired=False)
        transaction = GMTransaction(head="draft", payload={"team_id": team_id, "draft_slot": int(draft_idx)}, repaired=False)

        # Trade
        trade_pool = self._trade_pool(state, team_id)
        if trade_idx >= len(trade_pool) or not masks.trade[min(trade_idx, masks.trade.numel() - 1)]:
            if self.repair_illegal and len(trade_pool) > 0:
                trade_idx = 0
            else:
                trade_idx = -1
        if trade_idx >= 0:
            target = trade_pool[trade_idx]
            counterpart = self._cheapest_player(state, team_id)
            transaction = GMTransaction(
                head="trade",
                payload={
                    "team_id": team_id,
                    "target_player_id": target.player_id,
                    "secondary_player_id": counterpart.player_id,
                    "accept": True,
                },
                repaired=transaction.repaired or trade_idx < 0,
            )

        # Rotation templates -> minutes map
        rotation_payload = {"team_id": team_id, "minutes": self._rotation_template(state, team_id, rotation_idx)}
        if not masks.rotation[min(rotation_idx, self.spec.rotation_templates - 1)]:
            rotation_payload["minutes"] = {}
            rotation_payload["illegal"] = True
        rotation_txn = GMTransaction(head="rotation", payload=rotation_payload, repaired=False)

        # Contract
        contract_candidates = self._contract_pool(state, team_id)
        if contract_idx >= len(contract_candidates) or not masks.contract[min(contract_idx, masks.contract.numel() - 1)]:
            contract_idx = -1 if not self.repair_illegal else 0 if contract_candidates else -1
        contract_txn = GMTransaction(
            head="contract",
            payload={
                "team_id": team_id,
                "target_player_id": contract_candidates[contract_idx].player_id if contract_idx >= 0 and contract_candidates else -1,
                "contract_value": contract_candidates[contract_idx].contract.salary * 1.1 if contract_idx >= 0 and contract_candidates else 0.0,
                "contract_years": 3,
            },
            repaired=contract_idx < 0,
        )

        # Roster move
        roster_txn = self._roster_move(state, team_id, roster_idx, masks.roster_move)

        # Priority: roster moves > trades > contracts > rotation > draft
        chosen = roster_txn or transaction or contract_txn or rotation_txn
        chosen.reasons.extend(self.last_cba_block_reasons)
        chosen.reasons.extend(self.last_cba_warn_reasons)
        return chosen

    def _rotation_template(self, state: RosterState, team_id: int, template_idx: int) -> Dict[int, float]:
        team = state.get_team(team_id)
        players = [state.players[pid] for pid in team.roster]
        # Sort starters by minutes then age for deterministic ordering
        players = sorted(players, key=lambda p: (-p.minutes_per_game, p.age))
        minutes_map: Dict[int, float] = {}
        if template_idx == 0:
            for p in players:
                minutes_map[p.player_id] = p.minutes_per_game
        elif template_idx == 1:
            # Development template: give more to youngest
            players = sorted(players, key=lambda p: p.age)
            for i, p in enumerate(players):
                minutes_map[p.player_id] = 34.0 if i < 5 else 16.0
        elif template_idx == 2:
            # Veterans heavy
            players = sorted(players, key=lambda p: -p.age)
            for i, p in enumerate(players):
                minutes_map[p.player_id] = 33.0 if i < 5 else 14.0
        elif template_idx == 3:
            # Balanced
            for p in players:
                minutes_map[p.player_id] = 24.0
        elif template_idx == 4:
            # Small-ball: top guards/wings get more
            guards = [p for p in players if p.position.startswith("G")]
            others = [p for p in players if not p.position.startswith("G")]
            ordered = guards + others
            for i, p in enumerate(ordered):
                minutes_map[p.player_id] = 32.0 if i < 6 else 12.0
        else:
            # Default fallback: starter heavy
            for i, p in enumerate(players):
                minutes_map[p.player_id] = 35.0 if i < 5 else 10.0
        return minutes_map

    def _cheapest_player(self, state: RosterState, team_id: int) -> PlayerState:
        team = state.get_team(team_id)
        return min((state.players[pid] for pid in team.roster), key=lambda p: p.contract.salary)

    def _trade_pool(self, state: RosterState, team_id: int) -> List[PlayerState]:
        return [p for p in sorted(state.players.values(), key=lambda pl: pl.player_id) if p.team_id != team_id][: self.spec.trade_candidates]

    def _contract_pool(self, state: RosterState, team_id: int) -> List[PlayerState]:
        return [state.players[pid] for pid in state.get_team(team_id).roster]

    def _roster_move(self, state: RosterState, team_id: int, idx: int, mask: torch.Tensor) -> GMTransaction | None:
        # idx 0 = noop, 1 = waive cheapest, 2 = sign best free agent (none in mock so reuse cheapest from other team), else noop
        if idx == 0 or not mask[min(idx, mask.numel() - 1)]:
            return None
        if idx == 1:
            waive_id = self._cheapest_player(state, team_id).player_id
            return GMTransaction(head="roster_move", payload={"team_id": team_id, "waive_player_id": waive_id})
        if idx == 2:
            # pick first player not on team with lowest salary
            free_agent = min((p for p in state.players.values() if p.team_id != team_id), key=lambda p: p.contract.salary)
            return GMTransaction(
                head="roster_move",
                payload={"team_id": team_id, "sign_player_id": free_agent.player_id},
            )
        return None

    @staticmethod
    def _first_true_index(mask: torch.Tensor, default: int = 0) -> int:
        true_indices = torch.nonzero(mask, as_tuple=False)
        if true_indices.numel() == 0:
            return default
        return int(true_indices[0].item())
