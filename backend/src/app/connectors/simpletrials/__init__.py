"""SimpleTrials (CTMS) connector. Demo mode only for now; export import and API modes come next."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings

from .mock import MockStudyConnector
from .models import StudyConnector


def build_study_connector(settings: Settings) -> StudyConnector:
    # Only demo mode exists until SimpleTrials export files or API access are available.
    _ = settings.simpletrials_mode
    return MockStudyConnector(
        "Real studies will appear once a SimpleTrials export or API access is set up."
    )


@lru_cache
def get_study_connector() -> StudyConnector:
    return build_study_connector(get_settings())
