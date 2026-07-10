"""Celery worker fork-safety hooks.

When Celery uses prefork pool, child processes inherit ``_initialized = True``
from the parent but lose handler threads (threads don't survive ``fork()``).
``patch_celery_app()`` registers a ``worker_process_init`` signal handler
that calls ``configure(_force=True)`` to rebuild handlers in each child.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def patch_celery_app(celery_app: object) -> None:
    """Register ``worker_process_init`` hook on *celery_app* to re-init logging after fork.

    Parameters
    ----------
    celery_app:
        A ``celery.Celery`` instance.  The hook is attached via
        ``celery.signals.worker_process_init``.
    """
    try:
        from celery.signals import worker_process_init
    except ImportError:
        raise RuntimeError("celery not installed — pip install log-center-sdk[celery]")

    @worker_process_init.connect
    def _on_worker_fork(**_kwargs: object) -> None:
        from .core import configure

        configure(_force=True)
