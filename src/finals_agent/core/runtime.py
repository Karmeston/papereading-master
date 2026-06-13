from __future__ import annotations

from dataclasses import dataclass

from finals_agent.core.config import RuntimeSettings
from finals_agent.core.schemas import CourseContext, ResearchContext


@dataclass(frozen=True)
class AgentRuntime:
    """Runtime context shared by the CLI, agent factory, and tools.

    Keep this object small. It should describe how this run behaves, not store
    large documents or conversation history.
    """

    course_context: ResearchContext = ResearchContext()
    debug: bool = False
    max_search_results: int = 5

    @classmethod
    def default(cls) -> "AgentRuntime":
        return cls()

    @property
    def research_context(self) -> ResearchContext:
        return self.course_context

    @classmethod
    def from_settings(cls, settings: RuntimeSettings, course_context: ResearchContext | None = None) -> "AgentRuntime":
        return cls(
            course_context=course_context or ResearchContext(),
            debug=settings.debug,
            max_search_results=settings.max_search_results,
        )

    def with_course(self, course: str | None) -> "AgentRuntime":
        return self.with_field(course)

    def with_field(self, field: str | None) -> "AgentRuntime":
        return AgentRuntime(
            course_context=ResearchContext(
                field=field,
                focus=self.course_context.focus,
                target_document_id=self.course_context.target_document_id,
                target_title=self.course_context.target_title,
                review_mode=self.course_context.review_mode,
                goal=self.course_context.goal,
            ),
            debug=self.debug,
            max_search_results=self.max_search_results,
        )

    def with_target(self, document_id: str | None = None, title: str | None = None) -> "AgentRuntime":
        return AgentRuntime(
            course_context=ResearchContext(
                field=self.course_context.field,
                focus=self.course_context.focus,
                target_document_id=document_id or self.course_context.target_document_id,
                target_title=title or self.course_context.target_title,
                review_mode=self.course_context.review_mode,
                goal=self.course_context.goal,
            ),
            debug=self.debug,
            max_search_results=self.max_search_results,
        )

    def with_debug(self, debug: bool) -> "AgentRuntime":
        return AgentRuntime(
            course_context=self.course_context,
            debug=debug,
            max_search_results=self.max_search_results,
        )
