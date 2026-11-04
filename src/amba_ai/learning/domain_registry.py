from __future__ import annotations

from typing import Any, Sequence

from .domain_plugin import DomainPlugin
from .domains import ADAPTERS, PatternAdapter


class DomainRegistry:
    def __init__(
        self,
        adapters: Sequence[PatternAdapter] = ADAPTERS,
        plugins: Sequence[DomainPlugin] = (),
    ) -> None:
        self._adapters: list[PatternAdapter] = list(adapters)
        self._plugins: dict[str, DomainPlugin] = {
            p.domain_name.casefold(): p for p in plugins
        }
        self._init_default_plugins()

    def _init_default_plugins(self) -> None:
        try:
            from .domains.networking import NetworkingDomainPlugin
            self.register_plugin(NetworkingDomainPlugin())
        except Exception:
            pass

    def register(self, adapter: PatternAdapter) -> None:
        self._adapters.insert(0, adapter)

    def register_plugin(self, plugin: DomainPlugin) -> None:
        self._plugins[plugin.domain_name.casefold()] = plugin

    def get(self, name: str) -> PatternAdapter | None:
        target = name.casefold()
        for adapter in self._adapters:
            if adapter.name.casefold() == target:
                return adapter
        return None

    def get_plugin(self, name: str | None) -> DomainPlugin | None:
        if not name:
            return None
        return self._plugins.get(name.casefold())

    def resolve(self, text: str, metadata: dict[str, Any] | None = None) -> PatternAdapter:
        meta = metadata or {}
        scored: list[tuple[float, int, PatternAdapter]] = []

        for adapter in self._adapters:
            if adapter.name == "general":
                continue
            scored.append((adapter.score(text, meta), adapter.priority, adapter))

        if scored:
            score, _, best = max(scored, key=lambda item: (item[0], item[1]))
            if score >= 0.12:
                return best

        return next((a for a in self._adapters if a.name == "general"), self._adapters[-1])

    def resolve_plugin(self, text: str, metadata: dict[str, Any] | None = None) -> DomainPlugin | None:
        adapter = self.resolve(text, metadata)
        if adapter and adapter.name != "general":
            return self.get_plugin(adapter.name)
        return None

    def resolve_top_k(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
        k: int = 3,
    ) -> list[tuple[PatternAdapter, float]]:
        meta = metadata or {}
        scored = [
            (adapter, adapter.score(text, meta))
            for adapter in self._adapters
            if adapter.name != "general"
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:k]


domain_registry = DomainRegistry()