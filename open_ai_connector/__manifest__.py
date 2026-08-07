# -*- coding: utf-8 -*-
{
    'name': 'AI Connector for Odoo | Claude, ChatGPT, Gemini & Grok | AI Agent & Native AI Chat — No MCP Server | Use Your Subscription, No API Key',
    'version': '19.0.1.32.0',
    'category': 'Productivity/AI',
    'summary': 'Connect Odoo to Claude, ChatGPT, Gemini, Grok & 30+ AI/LLM providers. '
               'Run Odoo native AI agents & chat on your own subscription — no per-token '
               'API fees, no MCP server needed. OpenAI-compatible gateway. Free Bridge included.',
    'description': """
AI Connector — Multi-Provider AI for Odoo (Claude, ChatGPT, Gemini, Grok)
=========================================================================

Connect Odoo to ChatGPT, Claude, Gemini, Grok, DeepSeek, OpenRouter, AWS
Bedrock and 30+ AI / LLM providers — using the **AI subscription you already
pay for** instead of expensive per-million-token API billing.

Why this AI connector
---------------------
* **Use your existing subscription — no API key, no per-token fees.** Sign in
  with ChatGPT Plus/Pro, Claude Pro/Max, SuperGrok, Gemini or Qwen via OAuth
  and run Odoo AI on your flat monthly plan. Save hundreds of dollars a month.
* **No MCP server to host or expose.** Odoo 19's native AI Agents, AI fields
  and AI chat run DIRECTLY through this connector (via the free Bridge) — a
  simpler alternative to setting up an Odoo MCP server / Model Context Protocol
  endpoint to connect Claude, ChatGPT or other AI assistants to Odoo.
* **30+ AI / LLM providers** in one declarative catalog (OpenAI, Anthropic,
  Google Gemini, xAI Grok, AWS Bedrock, DeepSeek, OpenRouter, and more).
* **One Python method** — ``env['ai.connector'].chat(...)`` — same code for
  every provider, with normalised content, tool calls and token usage.
* **OpenAI-compatible HTTP gateway** (``/ai/v1/chat/completions``) — point
  LangChain, the OpenAI SDK, n8n or any AI agent at Odoo with an Odoo API key.
* **Built-in playground**, per-account credentials and full usage / cost logs.
* **Tool / function calling, streaming and vision** supported.
* **Free AI Connector Bridge included** — make Odoo 19's native AI Agents, AI
  fields and AI server actions run on your providers and subscription, for
  practically unlimited, worry-free AI chat with no per-token meter.

Keywords: Odoo AI, Odoo ChatGPT, Odoo Claude, Odoo Gemini, Odoo Grok, OpenAI,
Anthropic, LLM connector, AI agent, AI assistant, Odoo MCP server alternative,
Model Context Protocol (MCP), RAG, AI subscription, no API key, no per-token,
OpenAI-compatible gateway, multi-provider AI, natural language, Claude Desktop,
ChatGPT for Odoo, AI chat for Odoo 19.
""",
    'author': 'Roshan',
    'website': 'https://github.com/roshank8s/',
    'license': 'OPL-1',
    'price': 20.00,
    'currency': 'USD',
    'images': ['static/description/banner.png'],
    'depends': ['base', 'mail', 'web'],
    'data': [
        'security/ai_security.xml',
        'security/ir.model.access.csv',
        'data/ai_provider_data.xml',
        'data/ai_image_models_data.xml',
        'data/ai_provider_oauth_data.xml',
        'data/ai_cron_data.xml',
        'views/ai_provider_views.xml',
        'views/ai_credential_views.xml',
        'views/ai_model_views.xml',
        'views/ai_completion_log_views.xml',
        'views/ai_playground_views.xml',
        'views/ai_config_settings_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'open_ai_connector/static/src/js/oauth_auto_poll.js',
            'open_ai_connector/static/src/xml/oauth_auto_poll.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
