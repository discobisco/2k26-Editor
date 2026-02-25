from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from .adapters.ai_profile_repository import AiProfileRepository
from .adapters.cba_rules_adapter import CbaRulesAdapter
from .adapters.editor_live_gateway import EditorLiveGateway
from .adapters.gm_rl_adapter import GmRlAdapter
from .adapters.live_roster_snapshot_adapter import LiveRosterSnapshotAdapter
from .adapters.locker_room_profile_store import LockerRoomProfileStore
from .adapters.team_id_resolver import TeamIdResolver
from .api.v1.router import build_router
from .config import MCPServerSettings, get_settings
from .domain.cpu_ai_engine import CpuAiEngine
from .domain.coaching_engine import CoachingEngine
from .domain.draft_engine import DraftEngine
from .domain.dynasty_engine import DynastyEngine
from .domain.era_engine import EraEngine
from .domain.franchise_engine import FranchiseEngine
from .domain.franchise_direction_engine import FranchiseDirectionEngine
from .domain.locker_room_engine import LockerRoomEngine
from .domain.progression_engine import ProgressionEngine
from .domain.relocation_engine import RelocationEngine
from .domain.simulation_engine import SimulationEngine
from .domain.trade_engine import TradeEngine
from .logging import configure_logging
from .mcp.server import MyErasMCPServer
from .middleware.error_handler import register_exception_handlers
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.request_id import RequestIDMiddleware


class ServiceContainer:
    def __init__(self, settings: MCPServerSettings) -> None:
        self.settings = settings
        data_dir = Path(__file__).resolve().parent / "data" / "eras"
        ai_data_dir = Path(__file__).resolve().parent / "data" / "ai"
        profile_store_dir = Path(settings.profile_store_dir)

        self.cba_rules_adapter = CbaRulesAdapter()
        self.gm_rl_adapter = GmRlAdapter(seed=settings.default_seed)
        self.live_gateway = EditorLiveGateway(enable_live_writes=settings.enable_live_writes)
        self.team_id_resolver = TeamIdResolver()
        self.ai_profile_repository = AiProfileRepository(data_dir=ai_data_dir)
        self.locker_room_profile_store = LockerRoomProfileStore(root_dir=profile_store_dir)
        self.live_roster_snapshot_adapter = LiveRosterSnapshotAdapter(module_name=settings.module_name)

        self.era_engine = EraEngine(data_dir=data_dir)
        self.trade_engine = TradeEngine()
        self.franchise_engine = FranchiseEngine()
        self.draft_engine = DraftEngine()
        self.progression_engine = ProgressionEngine()
        self.simulation_engine = SimulationEngine()
        self.dynasty_engine = DynastyEngine()
        self.coaching_engine = CoachingEngine()
        self.relocation_engine = RelocationEngine()
        self.franchise_direction_engine = FranchiseDirectionEngine()
        self.cpu_ai_engine = CpuAiEngine(
            profile_repository=self.ai_profile_repository,
            team_resolver=self.team_id_resolver,
            direction_engine=self.franchise_direction_engine,
            default_seed=settings.default_seed,
            cache_max_entries=settings.ai_cache_max_entries,
            cache_ttl_seconds=settings.ai_cache_ttl_seconds,
        )
        self.locker_room_engine = LockerRoomEngine(
            profile_store=self.locker_room_profile_store,
            live_snapshot_adapter=self.live_roster_snapshot_adapter,
            default_seed=settings.default_seed,
            era_modifiers_path=ai_data_dir / "locker_room_era_modifiers.json",
        )

        self.mcp_server = MyErasMCPServer(self)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="NBA 2K MyEras MCP Server",
        version="0.1.0",
        description=(
            "Production-oriented MyEras simulation and optimization service with REST + MCP tool interfaces. "
            "This initial release is modern-era first."
        ),
    )
    container = ServiceContainer(settings)
    app.state.container = container

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)
    register_exception_handlers(app)

    app.include_router(build_router(container))
    return app
