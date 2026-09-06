from dataclasses import dataclass, field


@dataclass
class ChatTurn:
    role: str       # user / assistant
    content: str


@dataclass
class MemoryContext:
    """传给 RAG 的记忆上下文"""
    session_summary: str = ""
    recent_turns: list[ChatTurn] = field(default_factory=list)
    user_memories: list[str] = field(default_factory=list)      # Mem0 用户级
    session_memories: list[str] = field(default_factory=list)   # Mem0 会话级

    def has_content(self) -> bool:
        return bool(
            self.session_summary
            or self.recent_turns
            or self.user_memories
            or self.session_memories
        )