from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEPLOY = ROOT / "deploy"


def test_windows_schedule_uses_safe_cli_contract():
    script = (DEPLOY / "schedule_windows.ps1").read_text(encoding="utf-8")
    assert '-m backend.app.daily.cli update' in script
    assert '-m backend.app.daily.cli retrain' in script
    assert '"acquire", "train-local", "update", "retrain"' in script
    assert "-MultipleInstances IgnoreNew" in script
    assert "-RunOnlyIfNetworkAvailable" in script
    assert "shared operation lock" in script.lower()
    assert "cli bootstrap" not in script.lower()  # first model is never a scheduled side effect


def test_cron_retrain_is_gated_and_manual_phases_are_not_scheduled():
    cron = (DEPLOY / "badia-daily.crontab").read_text(encoding="utf-8")
    job_lines = [line for line in cron.splitlines() if line and not line.startswith("#")]
    assert len(job_lines) == 2
    assert any("cli update" in line for line in job_lines)
    assert any("cli retrain" in line for line in job_lines)
    assert all("cli acquire" not in line and "cli train-local" not in line for line in job_lines)
    assert "before network acquisition" in cron.lower()
    assert "shared daily-operation lock" in cron.lower()


def test_scheduling_guide_documents_failure_and_phase_boundaries():
    guide = (DEPLOY / "README_SCHEDULING.md").read_text(encoding="utf-8")
    for phrase in (
        "before any network request",
        "nonzero process result",
        "shared filesystem",
        "daily.cli acquire",
        "daily.cli train-local",
        "never retrains",
        "/api/health",
    ):
        assert phrase in guide
