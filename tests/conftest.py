"""Test bootstrap.

vertexai / google-cloud-aiplatform are heavy optional deps that are not needed to
test replication, leader election, or cache lifecycle logic. Stub them so the
suite runs anywhere, including CI without GCP credentials.
"""
import importlib.abc
import importlib.machinery
import sys
import types


class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        # Real classes rather than MagicMocks: director_agent subclasses one of
        # these at import time, and a MagicMock cannot be used as a base class.
        # Deriving from Exception also keeps `except Stub:` clauses legal.
        cls = type(name, (Exception,), {"__init__": lambda self, *a, **k: None})
        setattr(self, name, cls)
        return cls


class _StubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Supplies stub modules for GCP client libraries that are not installed.

    The allowlist is explicit rather than a broad "google.*" match, because
    `google.api_core` IS installed and is used for real in these tests --
    test_character_cache asserts on genuine NotFound/PermissionDenied classes.
    Shadowing it would make those assertions meaningless.

    Note that `google` and `google.cloud` are namespace packages, so they are
    deliberately absent from the list: the real ones must keep resolving.
    """

    PREFIXES = (
        "vertexai",
        "google.cloud.aiplatform",
        "google.cloud.storage",
        "google.cloud.firestore",
        "google.cloud.logging",
    )

    def find_spec(self, fullname, path=None, target=None):
        if not any(fullname == p or fullname.startswith(p + ".") for p in self.PREFIXES):
            return None
        return importlib.machinery.ModuleSpec(fullname, self, is_package=True)

    def create_module(self, spec):
        m = _StubModule(spec.name)
        m.__path__ = []
        return m

    def exec_module(self, module):
        pass


def pytest_configure(config):
    # Appended, never prepended, so a genuinely installed package always wins.
    # find_spec returns None for anything outside the allowlist, which makes this
    # a no-op in an environment with the full GCP SDK present.
    sys.meta_path.append(_StubFinder())


import pytest


@pytest.fixture
def fake_redis_server(monkeypatch):
    """Patches RedisBroadcaster to talk to one shared in-process Redis.

    Shared, not per-instance: the whole point of these tests is that separate
    Cloud Run instances see each other's writes, so they must hit the same
    keyspace and the same stream.
    """
    import fakeredis
    import fakeredis.aioredis

    import core.redis_broadcaster as rb

    server = fakeredis.FakeServer()

    def _from_url(url, **kwargs):
        return fakeredis.aioredis.FakeRedis(server=server, decode_responses=False)

    monkeypatch.setattr(rb, "aioredis", type("_M", (), {"from_url": staticmethod(_from_url)}))
    monkeypatch.setattr(rb, "REDIS_AVAILABLE", True)
    return _from_url
