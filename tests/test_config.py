"""Config path and settings tests."""

from event_concierge.config import CONFIG_DIR, DATA_DIR, PROJECT_ROOT, get_goals_config


def test_project_root_has_pyproject():
    assert (PROJECT_ROOT / "pyproject.toml").exists()


def test_config_files_exist():
    assert (CONFIG_DIR / "goals.yaml").exists()
    assert (CONFIG_DIR / "profile.yaml").exists()


def test_goals_config_loads():
    goals = get_goals_config()
    assert len(goals.goals) >= 3
    assert goals.thresholds.accept >= goals.thresholds.review


def test_data_dir_under_project():
    assert DATA_DIR.parent == PROJECT_ROOT
