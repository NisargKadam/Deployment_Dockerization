"""Deterministic rehearsal runnables. These are not LLM calls or real quality scores."""

import asyncio
import re

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.agent.workflow import Evaluation, build_humanizer_graph
from app.config import Settings


class DemoFailure(RuntimeError):
    """Intentional failure for the classroom trace investigation."""


def create_demo_graph(settings: Settings, scenario: str):
    passes = 0

    async def write(messages):
        nonlocal passes
        passes += 1
        await asyncio.sleep(2 if scenario == "slow" else 0.15)
        if scenario == "error":
            raise DemoFailure("Intentional classroom error in demo_writer")
        draft = re.search(
            r"<current_draft>(.*?)</current_draft>", messages[-1].content, flags=re.S
        ).group(1)
        for old, new in [
            ("Furthermore, ", ""),
            ("it is important to note that ", ""),
            ("leverage", "use"),
            ("utilize", "use"),
            ("in order to", "to"),
            ("operational ecosystem", "operations"),
        ]:
            draft = draft.replace(old, new)
        return AIMessage(content=draft[:1].upper() + draft[1:])

    async def evaluate(_messages):
        await asyncio.sleep(0.1)
        return Evaluation(
            score=72 if passes == 1 else 91,
            feedback=["Demo: try a second editing pass."] if passes == 1 else [],
        )

    return build_humanizer_graph(
        RunnableLambda(write, name="demo_writer"),
        RunnableLambda(evaluate, name="demo_evaluator"),
        score_threshold=settings.score_threshold,
        max_passes=settings.max_passes,
    )
