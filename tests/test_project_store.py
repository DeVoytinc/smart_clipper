from clipserver import project_store


def test_project_store_roundtrip(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    meta_path = data_dir / "projects.json"
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(project_store, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(project_store, "PROJECTS_META_PATH", str(meta_path))

    projects = [
        {"id": "p1", "name": "one"},
        {"id": "p2", "name": "two"},
    ]
    project_store.save_projects(projects)
    loaded = project_store.load_projects()
    assert loaded == projects

    all_projects, found = project_store.find_project("p2")
    assert len(all_projects) == 2
    assert found["name"] == "two"
