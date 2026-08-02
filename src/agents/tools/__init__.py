from src.agents.tools.calendar_tool import create_calendar_event, list_calendar_events
from src.agents.tools.reminder_tool import create_reminder, list_reminders
from src.agents.tools.summarize_tool import summarize_conversation

# example_tool.py's search_knowledge/calculate are left as unwired reference examples,
# not part of the production tool set.
ALL_TOOLS = [
    summarize_conversation,
    create_calendar_event,
    list_calendar_events,
    create_reminder,
    list_reminders,
]

__all__ = [
    "ALL_TOOLS",
    "summarize_conversation",
    "create_calendar_event",
    "list_calendar_events",
    "create_reminder",
    "list_reminders",
]
