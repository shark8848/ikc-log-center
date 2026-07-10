"""Unit tests for celery_hooks.py."""
from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock

import pytest


class TestPatchCeleryApp:
    def test_raises_without_celery(self):
        """When celery.signals is not importable, patch_celery_app raises RuntimeError."""
        # Temporarily hide celery from imports
        saved = {k: sys.modules.pop(k) for k in list(sys.modules) if k.startswith("celery")}
        sys.modules["celery"] = None  # type: ignore[assignment]
        sys.modules["celery.signals"] = None  # type: ignore[assignment]

        # Reload the module so its try/except ImportError triggers
        import log_center_sdk.celery_hooks as mod
        importlib.reload(mod)

        try:
            with pytest.raises(RuntimeError, match="celery not installed"):
                mod.patch_celery_app(MagicMock())
        finally:
            # Restore original modules
            for k in list(sys.modules):
                if k.startswith("celery"):
                    del sys.modules[k]
            sys.modules.update(saved)
            importlib.reload(mod)

    def test_registers_signal_when_celery_available(self):
        """If celery is installed, patch_celery_app should succeed without error."""
        try:
            from log_center_sdk.celery_hooks import patch_celery_app
            patch_celery_app(MagicMock())
        except RuntimeError:
            pytest.skip("celery not installed")
