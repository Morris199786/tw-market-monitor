"""Private ChatGPT Codex first; the original Responses API only on proven limit.

This module changes transport only. Article selection, deduplication, prompts,
structured schema, per-row checkpoint, API response recovery and publication
remain owned by research_ai_batch.py.
"""
import json
import os

from report_provider import plan_request


def research_first(*, raw_text, model, instructions, schema, api_call, response_id=None):
    # A previously persisted paid response must be polled, never POSTed again
    # and never replaced by a second Codex generation.
    if response_id:
        print('RESEARCH_PROVIDER api_resume_existing_response', flush=True)
        return api_call()

    if os.environ.get('RESEARCH_AI_ROUTE') != 'plan-first':
        raise RuntimeError('RESEARCH_PLAN_FIRST_REQUIRED: refusing direct paid API request')

    payload = {
        'task': 'research',
        'reasoning': {'effort': os.environ.get('RESEARCH_PLAN_EFFORT', 'high')},
        'instructions': instructions,
        'input': raw_text,
        'text': {'format': {'type': 'json_schema', 'name': 'research_article',
                            'strict': True, 'schema': schema}},
    }
    # The existing SSH client fails closed on connection and remote errors.
    # Do not turn those failures into API charges.
    answer = plan_request(payload)
    status = answer.get('status') if isinstance(answer, dict) else None
    if status == 'ok':
        txt = answer.get('text')
        if not isinstance(txt, str) or not txt.strip():
            raise RuntimeError('RESEARCH_CODEX_EMPTY: no paid API fallback')
        try:
            article = json.loads(txt)
        except (TypeError, ValueError) as exc:
            raise ValueError('RESEARCH_CODEX_JSON_INVALID: no paid API fallback') from exc
        if not (isinstance(article, dict) and isinstance(article.get('title'), str)
                and isinstance(article.get('summary'), list)
                and isinstance(article.get('blocks'), list) and article['blocks']):
            raise ValueError('RESEARCH_CODEX_ARTICLE_INVALID: no paid API fallback')
        print('RESEARCH_PROVIDER codex_subscription', flush=True)
        return article, {'provider': 'codex_subscription'}
    if status == 'plan_limit':
        print('RESEARCH_PROVIDER plan_limit_confirmed api_fallback', flush=True)
        if not os.environ.get('OPENAI_API_KEY'):
            raise RuntimeError('RESEARCH_API_FALLBACK_NO_KEY')
        return api_call()
    raise RuntimeError('RESEARCH_CODEX_UNEXPECTED_STATUS: no API fallback')
