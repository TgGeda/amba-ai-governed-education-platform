from __future__ import annotations

import weakref
from types import SimpleNamespace

from amba_ai.application.bootstrap import ApplicationBootstrap


def test_application_bootstrap_supports_qt_weak_reference_and_idempotent_close() -> None:
    calls: list[str] = []
    application = SimpleNamespace(stop=lambda: calls.append("stop"))
    bootstrap = ApplicationBootstrap(
        application=application,
        services=SimpleNamespace(),
    )

    reference = weakref.ref(bootstrap)
    assert reference() is bootstrap

    # QApplication.aboutToQuit can retain the bound method through a weak reference.
    callback = bootstrap.close
    callback()
    callback()

    assert calls == ["stop"]
    assert bootstrap._closed is True
