"""Built-in modules (roadmap 6.11.2). Adding a feature = adding a file here
and listing it in build_modules(); the core never changes."""

from ..core.modules import Module
from .ai_competitors_module import AiCompetitorsModule
from .ai_mentor_module import AiMentorModule
from .automation_module import AutomationModule
from .career_module import CareerModule
from .classroom_module import ClassroomModule
from .discord_module import DiscordModule
from .gamification_module import GamificationModule
from .knowledge_module import KnowledgeModule
from .leaderboards_module import LeaderboardsModule
from .multiplayer_module import MultiplayerModule
from .notifications_module import NotificationsModule
from .reporting_module import ReportingModule
from .scenarios_module import ScenariosModule


def build_modules() -> list[Module]:
    return [
        NotificationsModule(),
        AutomationModule(),
        GamificationModule(),
        AiMentorModule(),
        ReportingModule(),
        MultiplayerModule(),
        LeaderboardsModule(),
        DiscordModule(),
        ScenariosModule(),
        CareerModule(),
        ClassroomModule(),
        AiCompetitorsModule(),
        KnowledgeModule(),
    ]
