"""Registre des extracteurs par extension."""

from pathlib import Path

from voxpage.extract.base import ExtractOptions, Extractor, UnsupportedFormat

__all__ = [
    "ExtractOptions",
    "Extractor",
    "UnsupportedFormat",
    "extractor_for",
    "register",
    "supported_extensions",
]

_registry: dict[str, Extractor] = {}


def register(extractor: Extractor) -> None:
    for ext in extractor.extensions:
        _registry[ext.lower()] = extractor


def extractor_for(path: Path) -> Extractor:
    suffix = Path(path).suffix.lower()
    try:
        return _registry[suffix]
    except KeyError:
        raise UnsupportedFormat(f"Format non pris en charge : « {suffix or Path(path).name} ».") from None


def supported_extensions() -> list[str]:
    return sorted(_registry)


from voxpage.extract.text import TextExtractor  # noqa: E402

register(TextExtractor())
