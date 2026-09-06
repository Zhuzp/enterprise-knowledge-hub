from app.ai.memory.schemas import MemoryContext

SYSTEM_PROMPT = """你是企业内部知识库助手。

回答规则：
1. **优先依据「参考资料」**，资料里没有的不要说。
2. 「对话记忆」仅用于理解指代（如「刚才那个流程」）和用户偏好，不能与资料冲突。
3. 资料与记忆冲突时，以资料为准。
4. 回答简洁准确，使用中文。"""


def build_user_prompt(
    *,
    question: str,
    rag_context: str,
    memory: MemoryContext,
) -> str:
    sections: list[str] = []

    if memory.user_memories:
        sections.append("【用户长期记忆】\n" + "\n".join(f"- {m}" for m in memory.user_memories))

    if memory.session_memories:
        sections.append("【本会话记忆】\n" + "\n".join(f"- {m}" for m in memory.session_memories))

    if memory.session_summary:
        sections.append(f"【对话摘要】\n{memory.session_summary}")

    if memory.recent_turns:
        lines = [f"{t.role}: {t.content}" for t in memory.recent_turns]
        sections.append("【最近对话】\n" + "\n".join(lines))

    if rag_context:
        sections.append(f"【参考资料】\n{rag_context}")

    sections.append(f"【当前问题】\n{question}")
    return "\n\n".join(sections)