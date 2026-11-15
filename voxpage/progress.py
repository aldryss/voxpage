"""Progression et annulation."""

from collections.abc import Callable

ProgressCb = Callable[[str, float], None]  # (étape lisible, fraction 0..1)


class Cancelled(Exception):
    """Levée quand l'utilisateur annule l'opération."""


class CancelToken:
    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise Cancelled("Opération annulée.")
