from coclab.paths import base_dir


def test_base_dir_points_to_repo_in_dev():
    root = base_dir()
    assert (root / "coclab").is_dir()
    assert (root / "assets").is_dir()
