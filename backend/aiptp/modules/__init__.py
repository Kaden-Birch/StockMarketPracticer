"""Built-in modules (roadmap 6.11.2). Adding a feature = adding a file here
and listing it in build_modules(); the core never changes."""

from ..core.modules import Module
from .ai_mentor_module import AiMentorModule
from .automation_module import AutomationModule
from .gamification_module import GamificationModule
from .notifications_module import NotificationsModule
from .reporting_module import ReportingModule


def build_modules() -> list[Module]:
    return [
        NotificationsModule(),
        AutomationModule(),
        GamificationModule(),
        AiMentorModule(),
        ReportingModule(),
    ]
