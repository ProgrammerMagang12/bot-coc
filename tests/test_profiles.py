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


def test_ldplayer_index_from_port():
    assert profiles.ldplayer_index_for_address("127.0.0.1:5555") == 0
    assert profiles.ldplayer_index_for_address("127.0.0.1:5557") == 1
    assert profiles.ldplayer_index_for_address("127.0.0.1:5559") == 2
    assert profiles.ldplayer_index_for_address("127.0.0.1:5560") is None  # pola ganjil saja
    assert profiles.ldplayer_index_for_address("emulator-5554") is None
    assert profiles.ldplayer_index_for_address("192.168.1.5:5555") is None
