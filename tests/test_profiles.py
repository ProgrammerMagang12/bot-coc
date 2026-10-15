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
