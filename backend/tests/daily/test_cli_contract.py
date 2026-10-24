from backend.app.daily import cli
from backend.app.daily.store import Paths


def _paths(tmp_path):
    return Paths(tmp_path / "data", tmp_path / "models").ensure()


def test_train_local_never_constructs_network_or_loads_source_cells(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    monkeypatch.setattr(cli.Paths, "default", classmethod(lambda cls: paths))
    monkeypatch.setattr(cli, "Client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network constructed")))
    monkeypatch.setattr(cli, "load_cells", lambda *a, **k: (_ for _ in ()).throw(AssertionError("source cells loaded")))
    monkeypatch.setattr(cli, "run_retrain", lambda paths, force=False: {"action": "skipped", "reason": "not due"})
    assert cli.main(["train-local"]) == 0


def test_acquire_does_not_train_and_bootstrap_composes_phases(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    monkeypatch.setattr(cli.Paths, "default", classmethod(lambda cls: paths))
    calls = []
    monkeypatch.setattr(cli, "_acquire", lambda paths, args, **kwargs: calls.append("acquire") or {"action": "acquired"})
    monkeypatch.setattr(cli, "_train_local", lambda paths, force: calls.append("train") or {"action": "promoted", "passed": True})
    assert cli.main(["acquire"]) == 0 and calls == ["acquire"]
    calls.clear()
    assert cli.main(["bootstrap"]) == 0 and calls == ["acquire", "train"]


def test_retrain_checks_cadence_before_any_acquisition(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    monkeypatch.setattr(cli.Paths, "default", classmethod(lambda cls: paths))

    class FakeRegistry:
        def __init__(self, paths):
            pass

        def champion(self):
            return {"version": "existing", "promoted_at": "2026-01-01T00:00:00+00:00"}

    monkeypatch.setattr(cli, "Registry", FakeRegistry)
    monkeypatch.setattr(cli, "should_retrain", lambda manifest, champion: (False, "not enough new labels"))
    monkeypatch.setattr(cli, "refresh_training_data",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("acquisition occurred")))
    monkeypatch.setattr(cli, "Client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network constructed")))
    assert cli.main(["retrain"]) == 0


def test_update_failure_state_is_nonzero_for_scheduler(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    monkeypatch.setattr(cli.Paths, "default", classmethod(lambda cls: paths))
    monkeypatch.setattr(cli, "load_cells", lambda root: object())
    monkeypatch.setattr(cli, "_client", lambda paths: object())
    monkeypatch.setattr(cli, "run_update", lambda *a, **k: {"state": "fallback", "has_last_good": True})
    assert cli.main(["update"]) == 2
