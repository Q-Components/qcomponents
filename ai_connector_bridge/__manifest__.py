# -*- coding: utf-8 -*-
{
    'name': 'AI Connector Bridge for Odoo | Route Odoo Native AI, AI Agents & AI Fields to Claude, ChatGPT, Gemini & Grok | No MCP Server / Model Context Protocol | Use Your Subscription, No API Key | FREE',
    'version': '19.0.1.3.0',
    'category': 'Productivity/AI',
    'summary': "FREE companion bridge that makes Odoo 19's own built-in AI — AI Agents, "
               "AI fields, AI server actions and AI chat — run through the AI Connector, so "
               "Odoo native AI can use Claude, ChatGPT, Gemini, Grok, DeepSeek, OpenRouter and "
               "30+ providers on your own subscription or API keys. A simpler alternative to an "
               "Odoo MCP server / Model Context Protocol endpoint: it reuses Odoo's own tool-call "
               "loop and RAG. One Settings toggle, opt-in and safe (off = stock Odoo AI unchanged). "
               "Bundled free with the AI Connector app.",
    'description': """
==========================================================
AI Connector Bridge — Run Odoo Native AI on Any Provider
==========================================================

**AI Connector Bridge is a FREE companion to the AI Connector app.** It makes
Odoo 19's *own* built-in AI — **AI Agents, AI fields, AI server actions and AI
chat** — run **through the AI Connector** instead of Odoo's hardcoded
OpenAI / Google backend. The result: Odoo native AI can use **any** provider —
**Claude, ChatGPT, Gemini, Grok, DeepSeek, OpenRouter** and more — on **your own
subscription or API keys**.

Flip one switch in **Settings** — *Route Odoo AI through Connector* — pick a
**provider, account and model**, and every Agent, AI field and AI server action
in Odoo now answers through the connector. Turn it off and your stock Odoo AI is
exactly as before.

Why AI Connector Bridge
-----------------------

* **Free** — bundled at no cost with the AI Connector app.
* **Use your own provider & subscription** — point Odoo native AI at Claude,
  ChatGPT, Gemini, Grok, DeepSeek, OpenRouter and more, with no per-token
  vendor lock-in.
* **No MCP server needed** — a simpler alternative to standing up an Odoo MCP
  server / Model Context Protocol endpoint just to connect Claude or ChatGPT to
  Odoo. It works inside Odoo's existing AI plumbing.
* **Keeps Odoo's tool-calls & RAG** — it reuses Odoo's own tool-call loop, so
  function calling, RAG and AI server actions keep working.
* **Covers all of Odoo native AI** — AI Agents, AI fields, AI server actions
  and AI chat all route through the connector.
* **Opt-in & safe** — disabled by default; when off, Odoo's built-in AI behaves
  exactly as it always has.
* **One-toggle setup** — enable the bridge, choose provider / account / model,
  done. No code, no extra endpoint.

How it works
------------

The bridge routes Odoo's native LLM call to the AI Connector while reusing
Odoo's own tool-call loop and RAG. You configure providers, accounts and models
in the AI Connector; the bridge simply tells Odoo native AI to use them.

Requirements
------------

* Odoo 19 with the built-in **AI** module (``ai``)
* The **AI Connector** app (``open_ai_connector``)

Keywords: Odoo AI, Odoo 19 AI, Odoo native AI, Odoo AI Agent, Odoo AI agents, Odoo AI fields, Odoo AI server actions, Odoo AI chat, AI Connector, AI Connector Bridge, Claude Odoo, ChatGPT Odoo, Gemini Odoo, Grok Odoo, DeepSeek Odoo, OpenRouter Odoo, multi-provider LLM, AI assistant Odoo, MCP server, MCP server alternative, Model Context Protocol, no MCP server, RAG Odoo, tool calling, function calling, no API key, use your subscription, bring your own key, free Odoo AI module, route Odoo AI, Odoo LLM connector
""",
    'author': 'Roshan',
    'website': 'https://github.com/roshank8s/',
    'license': 'LGPL-3',
    'depends': ['ai', 'open_ai_connector'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'post_load': '_patch_llm_api_service',
    'installable': True,
    'application': False,
    'auto_install': False,
}
