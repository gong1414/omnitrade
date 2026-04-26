"""Infrastructure layer — DB, exchange adapters, LLM, vector store, news.

There is no aggregate ``InfrastructureContainer`` factory anymore; the
production wiring lives in :mod:`omnitrade.api.container` (the FastAPI
``ApiContainer``) and is built from :mod:`omnitrade.main._build_runtime_container`.
Each subpackage exposes its own narrow constructor (``CCXTExchange``,
``AgnoLLMAdapter.from_settings``, ``SQLiteVecStore``, ``NewsFetcher``)
and is consumed directly.
"""
