from coclab import profiles


def test_profile_roundtrip(tmp_path):
    data = {"device_address": "127.0.0.1:5555", "min_gold": 1}
    profiles.save_profile("acc1", data, tmp_path)
    assert profiles.list_profiles(tmp_path) == ["acc1"]
    assert profiles.load_profile("acc1", tmp_path) == data


def test_create_from_template(tmp_path):
    tpl = tmp_path / "src" / "tpl.json"
    tpl.parent.mkdir()
    tpl.write_text('{"device_address": "x", "min_dark": 0}', encoding="utf-8")
    target = tmp_path / "profil"
    profiles.create_from_template("acc2", tpl, target)
    assert profiles.load_profile("acc2", target)["device_address"] == "x"
    assert profiles.list_profiles(target) == ["acc2"]


def test_list_profiles_creates_dir(tmp_path):
    target = tmp_path / "sub"
    assert profiles.list_profiles(target) == []
    assert target.is_dir()


def test_merge_missing_fills_new_fields():
    data = {"min_gold": 1}
    template = {"min_gold": 2, "de_full_value": 300000, "coc_package": "x"}
    filled = profiles.merge_missing(data, template)
    assert filled == 2
    assert data["min_gold"] == 1  # yang sudah ada tidak ditimpa
    assert data["de_full_value"] == 300000


def test_rename_profile(tmp_path):
    profiles.save_profile("lama", {"min_gold": 1}, tmp_path)
    profiles.rename_profile("lama", "baru", tmp_path)
    assert profiles.list_profiles(tmp_path) == ["baru"]
    assert profiles.load_profile("baru", tmp_path)["min_gold"] == 1


def test_rename_profile_conflict(tmp_path):
    profiles.save_profile("a", {}, tmp_path)
    profiles.save_profile("b", {}, tmp_path)
    import pytest

    with pytest.raises(FileExistsError):
        profiles.rename_profile("a", "b", tmp_path)
