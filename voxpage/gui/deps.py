"""Dépendances injectables de l'interface (permet un faux pipeline dans l'auto-test)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class GuiDeps:
    convert: Callable[..., Any]  # pipeline.convert(input, output, settings, progress, cancel)
    extract_text: Callable[..., str]  # pipeline.extract_text(input, settings, progress, cancel)
    engine_factory: Callable[[], Any]  # -> objet avec list_voices() et synthesize()
    extensions: Callable[[], list[str]]
    load_settings: Callable[[], Any]
    save_settings: Callable[[Any], None]


def default_deps() -> GuiDeps:
    """Dépendances réelles ; les modules lourds ne sont importés qu'à l'appel."""

    def convert(*args: Any, **kwargs: Any) -> Any:
        from voxpage import pipeline

        return pipeline.convert(*args, **kwargs)

    def extract_text(*args: Any, **kwargs: Any) -> str:
        from voxpage import pipeline

        return pipeline.extract_text(*args, **kwargs)

    def engine_factory() -> Any:
        from voxpage.tts.sherpa import get_engine

        return get_engine()

    def extensions() -> list[str]:
        from voxpage import extract

        return extract.supported_extensions()

    def load_settings() -> Any:
        from voxpage import settings

        return settings.load()

    def save_settings(s: Any) -> None:
        from voxpage import settings

        settings.save(s)

    return GuiDeps(convert, extract_text, engine_factory, extensions, load_settings, save_settings)
