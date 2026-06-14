"""Agent module - LangGraph-based multi-agent system.

Agents:
- Parse Agent: Resume text → structured data (Phase 1)
- Match Agent: Resume + Jobs → top recommendations (Phase 2)
- Question Agent: Resume + Job + RAG → interview questions (Phase 3)
- Interview Agent: ReAct loop for interview conversation (Phase 4)
- Score Agent: Full interview data → report (Phase 5)
"""