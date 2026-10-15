from coclab import pinch


def test_script_has_two_fingers_and_converging_moves():
    s = pinch.build_pinch_out_script()
    assert f"sendevent {pinch.TOUCH_DEVICE} 3 47 0" in s   # slot 0 turun
    assert f"sendevent {pinch.TOUCH_DEVICE} 3 47 1" in s   # slot 1 turun
    assert " 410" in s and " 490" in s                     # posisi akhir jari (saling mendekat)
    assert s.count(" 330 1") == 1 and s.count(" 330 0") == 1  # BTN_TOUCH down/up


def test_script_downs_ups_and_syn():
    s = pinch.build_pinch_out_script(steps=3)
    assert f"sendevent {pinch.TOUCH_DEVICE} 0 0 0" in s          # SYN_REPORT
    assert f"sendevent {pinch.TOUCH_DEVICE} 3 57 -1" in s        # tracking up
    assert s.startswith("sendevent")


def test_write_cmd_heredoc():
    cmd = pinch.write_script_cmd()
    assert cmd.startswith("cat > /data/local/tmp/coclab_pinch_out.sh << 'COCLAB_EOF'")
    assert "chmod 755 /data/local/tmp/coclab_pinch_out.sh" in cmd
    # heredoc benar-benar tertutup (delimiter buka + tutup), bukan satu saja:
    assert cmd.count("COCLAB_EOF") == 2
