"""Bounded ordinary-chat context, separate from private evidence and experiments."""

import json
import re
from typing import Literal

from pydantic import Field

from .schemas import StrictModel


class ContextMessage(StrictModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=1200)


class ConversationContext(StrictModel):
    messages: list[ContextMessage] = Field(default_factory=list, max_length=8)
    source_message_ids: list[int] = Field(default_factory=list, max_length=8)
    boundary: Literal['start', 'budget', 'ineligible_turn', 'malformed_turn'] = 'start'

    def summary(self):
        return {'mode': 'bounded_ordinary_chat_v1', 'messageCount': len(self.messages), 'characterCount': sum(len(item.content) for item in self.messages), 'sourceMessageIds': self.source_message_ids, 'boundary': self.boundary, 'privateEvidenceIncluded': False, 'oldSourcesIncluded': False}


def safe_ordinary_text(text: str) -> bool:
    if not isinstance(text, str) or not text.strip() or len(text) > 1200:
        return False
    # Never propagate credentials, evidence locators or file payloads as chat
    # memory. This is a conservative boundary, not a general DLP classifier.
    return not re.search(r'sk-[A-Za-z0-9_-]{12,}|Bearer\s+\S+|(?:api[_ -]?key|password|密码|密钥|token)\s*[:=：]\s*\S+|https?://|\[local:|\b10\.\d{4,9}/|上传\s*(?:CSV|PDF|文件)\s*[:：]|/Users/|/tmp/|-----BEGIN', text, re.I)


def select_conversation_context(rows: list[dict], max_pairs: int = 4, max_characters: int = 6000) -> ConversationContext:
    """Take a contiguous eligible suffix; never jump across a private/tool turn.

    Rows must be chronological and already scoped to exactly one session.
    Unlabelled historical rows are deliberately not backfilled into model input.
    """
    pairs, identifiers, size = [], [], 0
    max_characters = min(max_characters, 6000)
    boundary = 'start'
    index = len(rows) - 1
    while index >= 0:
        if len(pairs) >= min(max_pairs, 4):
            boundary = 'budget'
            break
        if index < 1 or rows[index].get('role') != 'assistant' or rows[index-1].get('role') != 'user':
            boundary = 'malformed_turn'
            break
        user, assistant = rows[index-1], rows[index]
        try:
            metadata = json.loads(assistant.get('result_json') or '{}')
        except (TypeError, ValueError):
            boundary = 'malformed_turn'
            break
        texts = [user.get('content'), assistant.get('content')]
        eligible = isinstance(metadata, dict) and metadata.get('contextKind') == 'ordinary_chat_v1' and metadata.get('contextEligible') is True
        excluded = isinstance(metadata, dict) and any(metadata.get(key) for key in ('sources', 'privateEvidence', 'analysis', 'agent', 'methodSummary', 'experimentReport', 'experimentPlan', 'toolResults'))
        if not eligible or excluded or not all(safe_ordinary_text(text) for text in texts):
            boundary = 'ineligible_turn'
            break
        if size + sum(map(len, texts)) > max_characters:
            boundary = 'budget'
            break
        size += sum(map(len, texts))
        pairs.insert(0, [ContextMessage(role='user', content=texts[0]), ContextMessage(role='assistant', content=texts[1])])
        identifiers[0:0] = [user['id'], assistant['id']]
        index -= 2
    return ConversationContext(messages=[message for pair in pairs for message in pair], source_message_ids=identifiers, boundary=boundary)

