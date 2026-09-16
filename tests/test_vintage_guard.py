from apps.research.vintage_guard import assess_dataset


def test_revised_history_is_not_treated_as_point_in_time_vintage():
    assessment = assess_dataset(
        dataset_revision_status="revised_history",
        has_observation_level_release_vintage=True,
        execution_grade=False,
    )
    assert assessment.allowed_for_causal_backtest is False


def test_point_in_time_requires_observation_level_vintage():
    assessment = assess_dataset(
        dataset_revision_status="point_in_time_vintage",
        has_observation_level_release_vintage=False,
        execution_grade=False,
    )
    assert assessment.allowed_for_causal_backtest is False


def test_reference_data_never_becomes_execution_grade():
    assessment = assess_dataset(
        dataset_revision_status="point_in_time_vintage",
        has_observation_level_release_vintage=True,
        execution_grade=True,
    )
    assert assessment.allowed_for_causal_backtest is False


def test_valid_point_in_time_reference_dataset_can_be_used_for_research():
    assessment = assess_dataset(
        dataset_revision_status="point_in_time_vintage",
        has_observation_level_release_vintage=True,
        execution_grade=False,
    )
    assert assessment.allowed_for_causal_backtest is True
