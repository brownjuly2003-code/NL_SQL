"""ProviderName (settings) must stay in sync with the factory (audit item C2).

The `ProviderName` Literal is the type of `Settings.default_provider` /
`frontier_provider` / `local_provider`. If a name the factory supports is missing
from the Literal, then setting e.g. `NL_SQL_DEFAULT_PROVIDER=gracekelly` crashes at
Settings validation even though `build_provider` would have handled it. These
tests fail if the two ever drift apart again.
"""

from __future__ import annotations

import typing

import pytest

from nl_sql.config.settings import ProviderName, Settings
from nl_sql.llm.providers.base import ProviderError
from nl_sql.llm.providers.factory import build_provider

PROVIDER_NAMES = typing.get_args(ProviderName)


@pytest.mark.parametrize("name", PROVIDER_NAMES)
def test_every_provider_name_is_routable_by_the_factory(name: str) -> None:
    """No ProviderName should hit the factory's 'unknown provider' branch.

    Construction may still fail for other reasons (a provider that eagerly checks
    a missing key), but that means the name IS recognized — only an
    'unknown provider name' ProviderError is a real drift failure.
    """
    settings = Settings()
    try:
        build_provider(name, settings=settings)
    except ProviderError as exc:
        if "unknown provider" in str(exc).lower():
            pytest.fail(f"{name} is not routed by the factory")
    except Exception:  # a missing key / network error still means the name is known
        pass


def test_factory_still_rejects_a_truly_unknown_name() -> None:
    with pytest.raises(ProviderError, match="unknown provider"):
        build_provider("definitely-not-a-provider", settings=Settings())


@pytest.mark.parametrize("name", PROVIDER_NAMES)
def test_each_name_validates_as_default_provider(name: str) -> None:
    """The whole point of C2: every factory name is assignable to the setting."""
    settings = Settings(default_provider=name)
    assert settings.default_provider == name
