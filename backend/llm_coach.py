"""
LLM Coach — builds game-context system prompts and streams LLM API responses.

Uses OpenAI SDK with base_url override for any OpenAI-compatible API
(DeepSeek, Alibaba DashScope, local Ollama, etc.).
Conversation history is per-round (cleared on new round).
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Generator

from openai import OpenAI

logger = logging.getLogger(__name__)

# Configuration from environment (supports any OpenAI-compatible API)
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen-plus")

SYSTEM_PROMPT_TEMPLATE = """\
你是一位日本麻将（立直麻将）教练。用中文回答，简洁明了，每次不超过200字。

## 牌面记法

输入记法: 1m-9m(万) 1p-9p(饼) 1s-9s(索), 0m/0p/0s=赤五(赤ドラ,+1翻), E/S/W/N=東南西北, P=白 F=發 C=中。
**回答时必须用中文牌名**：说"一万""赤五饼""九索""東""白"等，禁止用1m/2p/3s等代码。

## 分析规则

1. **以当前状态为准**：下方牌局状态是实时的，之前对话中的牌局信息可能已过时。严格基于当前手牌、牌河、副露分析。
2. **引用 Mortal AI 分析时注意 Q-value 差距**：
   - Q-value 接近的候选牌（差距<0.3）说明多种打法均合理，不必死守第一名，可以结合局势讨论各自优劣
   - Q-value 差距大的（差距>1.0）说明最优选明显优于其他，应明确推荐
   - 介于两者之间的，说明有倾向但不绝对
3. **分析框架**（按需选用，不必每次全写）：
   - 手牌构成：搭子/面子/孤张识别，块(block)理论
   - 进张效率：各候选切牌的有效进张数、牌河中已见张数
   - 攻防判断：根据巡目、向听数、他家牌河/副露/立直状态判断攻守时机
   - 局势因素：点数差、场风、dora关联
4. **禁止自相矛盾**：如果说一张牌"已出现在牌河"就不能同时说它"容易放铳"。先确认事实，再下结论。
5. **不确定时诚实说明**：麻将有运气成分，如果局面确实模糊，说"这里两种打法都可以"比强行找理由更好。

{game_context}"""

WIND_CHARS = {"E": "東", "S": "南", "W": "西", "N": "北"}
SEAT_LABELS = ["自家", "下家", "対面", "上家"]


def is_available() -> bool:
    """Check if LLM coach is configured (API key present)."""
    return bool(LLM_API_KEY)


class LLMCoach:
    """Manages LLM conversation for one game session."""

    def __init__(self):
        self._client: Optional[OpenAI] = None
        self._history: list[dict] = []  # user/assistant messages only

        if LLM_API_KEY:
            self._client = OpenAI(
                api_key=LLM_API_KEY,
                base_url=LLM_BASE_URL,
            )

    @property
    def available(self) -> bool:
        return self._client is not None

    def clear_history(self) -> None:
        """Clear conversation history (call on new round)."""
        self._history.clear()

    def stream_reply(
        self, user_message: str, game_context: str
    ) -> Generator[str, None, None]:
        """Stream a reply from the LLM given user message and game context.

        Yields incremental text chunks. Appends full exchange to history.
        """
        if not self._client:
            yield "未配置 API Key，无法使用 AI 教练。"
            return

        # Truncate message
        user_message = user_message[:500]

        # Build messages
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(game_context=game_context)
        messages = [
            {"role": "system", "content": system_prompt},
            *self._history,
            {"role": "user", "content": user_message},
        ]

        try:
            stream = self._client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                stream=True,
                max_tokens=300,
                temperature=0.7,
            )

            full_reply = []
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_reply.append(text)
                    yield text

            # Save to history
            self._history.append({"role": "user", "content": user_message})
            self._history.append({"role": "assistant", "content": "".join(full_reply)})

        except Exception as e:
            logger.exception(f"LLM API error: {e}")
            yield f"AI 教练暂时不可用: {e}"


def build_game_context(game_context: dict) -> str:
    """Build the game context string for the system prompt.

    Args:
        game_context: dict from WebAgent.get_game_context()
    """
    lines = ["[当前牌局状态]"]

    round_wind = WIND_CHARS.get(game_context.get("round_wind", ""), "?")
    round_num = game_context.get("round_number", 0)
    honba = game_context.get("honba", 0)
    lines.append(f"场风: {round_wind}  局数: {round_wind}{round_num + 1}局  本場: {honba}")

    lines.append(f"巡目: {game_context.get('turn_number', '?')}")

    seat_wind = game_context.get("seat_wind", "?")
    lines.append(f"自风: {WIND_CHARS.get(seat_wind, seat_wind)}")

    hand = game_context.get("hand", [])
    lines.append(f"手牌: {' '.join(hand)}")

    melds = game_context.get("melds", [])
    if melds:
        meld_strs = []
        for m in melds:
            tiles_str = "".join(m.get("tiles", []))
            meld_type = m.get("type", "")
            meld_strs.append(f"{tiles_str}({meld_type})")
        lines.append(f"副露: {' '.join(meld_strs)}")
    else:
        lines.append("副露: 无")

    draw = game_context.get("draw_tile")
    if draw:
        lines.append(f"摸牌: {draw}")

    shanten = game_context.get("shanten")
    if shanten is not None:
        lines.append(f"向听数: {shanten}")

    dora = game_context.get("dora_indicators", [])
    if dora:
        lines.append(f"ドラ表示牌: {' '.join(dora)}")

    # Scores
    scores = game_context.get("scores", [])
    if scores:
        score_parts = [f"{SEAT_LABELS[i]}{scores[i]}" for i in range(min(4, len(scores)))]
        lines.append(f"点数: {' '.join(score_parts)}")

    # Other players' visible info
    opponents = game_context.get("opponents", [])
    if opponents:
        lines.append("")
        lines.append("[其他家可见信息]")
        for opp in opponents:
            label = opp.get("label", "?")
            discards = " ".join(opp.get("discards", []))
            opp_melds = opp.get("melds", [])
            meld_str = "无"
            if opp_melds:
                parts = []
                for m in opp_melds:
                    parts.append("".join(m.get("tiles", [])) + f"({m.get('type', '')})")
                meld_str = " ".join(parts)
            status = ""
            if opp.get("is_riichi"):
                status = " 立直中"
            lines.append(f"{label}牌河: {discards}  副露: {meld_str}{status}")

    # Coach analysis (Mortal)
    coach = game_context.get("coach_analysis")
    if coach:
        lines.append("")
        lines.append("[AI教练分析 (Mortal)]")
        rec = coach.get("recommended", "?")
        lines.append(f"推荐打: {rec}")
        candidates = coach.get("candidates", [])
        if candidates:
            top_score = candidates[0].get("score", 0) if candidates else 0
            lines.append("候选牌 (Q-value越高越优):")
            for c in candidates[:5]:
                tile = c.get("tile", "?")
                score = c.get("score", 0)
                gap = top_score - score
                suffix = " ← 推荐" if tile == rec else ""
                if gap < 0.01:
                    gap_hint = ""
                elif gap < 0.3:
                    gap_hint = " (与最优差距小，也可考虑)"
                elif gap < 1.0:
                    gap_hint = " (略逊于最优)"
                else:
                    gap_hint = " (明显弱于最优)"
                lines.append(f"  {tile}: Q={score:.2f}{gap_hint}{suffix}")

    return "\n".join(lines)
