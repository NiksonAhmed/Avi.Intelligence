"""SimpleTrials (CTMS) connector: read-only API when credentials are set, otherwise demo studies."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings

from .api_client import SimpleTrialsClient
from .live import ApiStudyConnector
from .mapping import parse_key_names
from .mock import MockStudyConnector
from .models import StudyConnector


def build_study_connector(settings: Settings) -> StudyConnector:
    scope = settings.simpletrials_scope
    if settings.simpletrials_mode == "mock":
        return MockStudyConnector("SIMPLETRIALS_MODE is set to mock.")
    if scope is None:
        if settings.simpletrials_mode == "api":
            raise RuntimeError(
                "SIMPLETRIALS_MODE=api but neither SIMPLETRIALS_CUSTOMER_ID/KEY nor "
                "SIMPLETRIALS_STUDY_ID/KEY is set."
            )
        return MockStudyConnector(
            "Real studies will appear once SimpleTrials API credentials are set "
            "(see docs/simpletrials-setup.md)."
        )
    if scope == "workspace":
        account_id, key = settings.simpletrials_customer_id, settings.simpletrials_customer_key
    else:
        account_id, key = settings.simpletrials_study_id, settings.simpletrials_study_key
    assert account_id is not None and key is not None  # guaranteed by simpletrials_scope
    return ApiStudyConnector(
        SimpleTrialsClient(
            base_url=settings.simpletrials_base_url,
            scope=scope,
            account_id=account_id,
            key=key.get_secret_value(),
        ),
        key_names=parse_key_names(settings.simpletrials_key_milestones),
    )


@lru_cache
def get_study_connector() -> StudyConnector:
    return build_study_connector(get_settings())
