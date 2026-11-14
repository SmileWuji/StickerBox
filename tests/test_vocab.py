from pathlib import Path

import pytest

import factory
from sticker_box import script_check, vocab

GENERIC = Path(__file__).resolve().parent.parent / "testdata" / "generic"
STICKER = ["--license", "unknown", "--text", "", "--note", "test"]


@pytest.fixture
def sbox(tmp_path, run_cli):
    root = tmp_path / "s"
    run_cli("init", str(root), "--preset", "telegram-sticker", "--language", "zh-Hans")
    return root


def add_sticker(run_cli, root, tmp_path, seed, *tag_args):
    path = factory.write_webp(tmp_path / f"{seed}.webp", factory.picture(seed, (512, 512), alpha=True))
    (staged,) = run_cli("stage", str(path), "--box", str(root))["results"]
    return run_cli("commit", staged["ref"], "--box", str(root), *STICKER, *tag_args)


def test_similarity_orders_sensibly():
    assert vocab.similarity("无语", "无语了") > vocab.similarity("无语", "开心")
    assert vocab.similarity("Happy", "happy!") == 1.0
    assert vocab.similarity("", "x") == 0.0


@pytest.mark.parametrize("text, language, warns", [
    ("无语", "zh-Hans", False), ("やれやれ", "zh-Hans", True), ("やれやれ", "ja", False),
    ("speechless", "zh-Hans", True), ("speechless", "en", False), ("无语", "en", True), ("OK!", "en", False),
])
def test_script_check(text, language, warns):
    assert (script_check.mismatch(text, language) is not None) is warns


def test_tag_new_define_alias_and_list(sbox, run_cli):
    box = ["--box", str(sbox)]
    out = run_cli("tag", "new", "emotion", "无语", "--means", "说不出话的无奈", "--alias", "无言", *box)
    assert out["tag"] == "emotion=无语" and out["warnings"] == []
    assert run_cli("tag", "new", "emotion", "无言", "--means", "x", *box, expect=1)["error"] == "exists"
    run_cli("tag", "define", "emotion", "无语", "无话可说", *box)
    (tag,) = run_cli("tag", "list", *box)["tags"]
    assert tag["definition"] == "无话可说" and tag["aliases"] == ["无言"] and tag["uses"] == 0
    assert run_cli("tag", "new", "mood", "x", "--means", "x", *box, expect=1)["error"] == "unknown_category"
    out = run_cli("tag", "new", "emotion", "speechless", "--means", "x", *box)
    assert out["warnings"]


def test_alias_resolves_at_commit(sbox, run_cli, tmp_path):
    box = ["--box", str(sbox)]
    run_cli("tag", "new", "emotion", "无语", "--means", "说不出话", "--alias", "无言", *box)
    out = add_sticker(run_cli, sbox, tmp_path, 1, "--tag", "emotion=无言")
    assert out["tags"] == ["emotion=无语"]


def test_merge_retags_items_and_keeps_an_alias(sbox, run_cli, tmp_path):
    box = ["--box", str(sbox)]
    a = add_sticker(run_cli, sbox, tmp_path, 1, "--define", "emotion=无语", "说不出话")
    b = add_sticker(run_cli, sbox, tmp_path, 2, "--define", "emotion=无语了", "说不出话了")
    review = run_cli("vocab", "review", *box)
    (pair,) = review["similar_pairs"]
    assert {pair["a"]["value"], pair["b"]["value"]} == {"无语", "无语了"}
    out = run_cli("tag", "merge", "emotion", "无语了", "无语", *box)
    assert out["items_retagged"] == 1
    assert run_cli("show", b["ref"], *box)["tags"] == ["emotion=无语"]
    (tag,) = run_cli("tag", "list", *box)["tags"]
    assert tag["aliases"] == ["无语了"] and tag["uses"] == 2
    assert run_cli("show", a["ref"], *box)["tags"] == ["emotion=无语"]


def test_rename_keeps_old_value_as_alias(sbox, run_cli, tmp_path):
    box = ["--box", str(sbox)]
    add_sticker(run_cli, sbox, tmp_path, 1, "--define", "emotion=无语", "说不出话")
    run_cli("tag", "rename", "emotion", "无语", "无话可说", *box)
    out = add_sticker(run_cli, sbox, tmp_path, 2, "--tag", "emotion=无语")
    assert out["tags"] == ["emotion=无话可说"]


def test_retired_tags_are_refused_on_new_items(sbox, run_cli, tmp_path):
    box = ["--box", str(sbox)]
    add_sticker(run_cli, sbox, tmp_path, 1, "--define", "emotion=无语", "说不出话")
    run_cli("tag", "retire", "emotion", "无语", *box)
    path = factory.write_webp(tmp_path / "x.webp", factory.picture(9, (512, 512)))
    (staged,) = run_cli("stage", str(path), *box)["results"]
    out = run_cli("commit", staged["ref"], *box, *STICKER, "--tag", "emotion=无语", expect=1)
    assert out["problems"][0]["problem"] == "retired_tag"
    run_cli("tag", "retire", "emotion", "无语", "--restore", *box)
    run_cli("commit", staged["ref"], *box, *STICKER, "--tag", "emotion=无语")


def test_parent_refuses_cycles(sbox, run_cli):
    box = ["--box", str(sbox)]
    run_cli("tag", "new", "emotion", "负面", "--means", "不好的情绪", *box)
    run_cli("tag", "new", "emotion", "嫌弃", "--means", "看不上", "--parent", "负面", *box)
    assert run_cli("tag", "parent", "emotion", "负面", "嫌弃", *box, expect=1)["error"] == "cycle"
    run_cli("tag", "parent", "emotion", "嫌弃", *box)
    tags = {t["value"]: t for t in run_cli("tag", "list", *box)["tags"]}
    assert tags["嫌弃"]["parent"] is None


def test_lock_requires_tag_new(sbox, run_cli, tmp_path):
    box = ["--box", str(sbox)]
    add_sticker(run_cli, sbox, tmp_path, 1, "--define", "emotion=无语", "说不出话")
    assert run_cli("vocab", "lock", *box) == {"vocabulary": "locked", "was": "open"}
    path = factory.write_webp(tmp_path / "x.webp", factory.picture(9, (512, 512)))
    (staged,) = run_cli("stage", str(path), *box)["results"]
    out = run_cli("commit", staged["ref"], *box, *STICKER, "--define", "emotion=开心", "高兴", expect=1)
    assert "tag new" in out["problems"][0]["message"]
    run_cli("tag", "new", "emotion", "开心", "--means", "高兴", *box)
    run_cli("commit", staged["ref"], *box, *STICKER, "--tag", "emotion=开心")
    assert "Vocabulary is locked" in (sbox / "README.md").read_text()


def test_free_vocabulary_creates_on_first_use_and_reuses_case_twins(tmp_path, run_cli):
    root = tmp_path / "g"
    run_cli("init", str(root), "--preset", "gallery", "--language", "en")
    (a,) = run_cli("stage", str(GENERIC / "sticker-static.webp"), "--box", str(root))["results"]
    run_cli("commit", a["ref"], "--box", str(root), "--license", "unknown", "--tag", "Cat")
    (b,) = run_cli("stage", str(GENERIC / "animated.gif"), "--box", str(root))["results"]
    out = run_cli("commit", b["ref"], "--box", str(root), "--license", "unknown", "--tag", "cat")
    assert out["tags"] == ["tag=Cat"] and out["warnings"]


def test_readme_lists_the_vocabulary(sbox, run_cli, tmp_path):
    add_sticker(run_cli, sbox, tmp_path, 1, "--define", "emotion=无语", "说不出话 | 有竖线")
    readme = (sbox / "README.md").read_text()
    assert "| 无语 | 说不出话 \\| 有竖线 |  |  | 1 |" in readme


def test_mixed_script_names_pass_the_script_check():
    assert script_check.mismatch("Moka酱", "zh-Hans") is None
    assert script_check.mismatch("MokaPackX", "zh-Hans") is not None


def test_alias_use_is_reported(sbox, run_cli, tmp_path):
    run_cli("tag", "new", "emotion", "无语", "--means", "说不出话", "--alias", "无言", "--box", str(sbox))
    out = add_sticker(run_cli, sbox, tmp_path, 1, "--tag", "emotion=无言")
    assert any("alias" in w for w in out["warnings"])


def test_merge_reports_items_that_already_had_the_target(sbox, run_cli, tmp_path):
    box = ["--box", str(sbox)]
    run_cli("tag", "new", "emotion", "傲娇", "--means", "嘴硬心软", *box)
    add_sticker(run_cli, sbox, tmp_path, 1, "--define", "emotion=理直气壮", "理不直气也壮", "--tag", "emotion=傲娇")
    out = run_cli("tag", "merge", "emotion", "傲娇", "理直气壮", *box)
    assert out["items_retagged"] == 0 and out["items_already_tagged"] == 1 and "1 item(s) lost" in out["message"]


def test_name_categories_skip_the_script_check(sbox, run_cli, tmp_path):
    out = add_sticker(run_cli, sbox, tmp_path, 31, "--define", "emotion=开心", "高兴",
                      "--define", "pack=MokaPackX", "a pack", "--define", "character=Moka", "a character")
    warned = " ".join(out.get("warnings", []))
    assert "pack=MokaPackX" not in warned and "character=Moka" in warned
    assert run_cli("tag", "new", "pack", "OtherPack", "--means", "another pack", "--box", str(sbox))["warnings"] == []
    assert run_cli("tag", "new", "visual", "Smile", "--means", "x", "--box", str(sbox))["warnings"]
    readme = (sbox / "README.md").read_text()
    assert "`pack` (optional, one or more values, proper names in any script)" in readme


def test_name_flag_is_validated_and_old_policies_still_load(sbox, run_cli, tmp_path):
    run_cli("policy", "set", "categories", '{"emotion": {"required": true}, "pack": {"names": "yes"}}', "--box", str(sbox), expect=1)
    run_cli("policy", "set", "categories", '{"emotion": {"required": true}, "pack": {}}', "--box", str(sbox))
    shown = run_cli("policy", "show", "categories", "--box", str(sbox))["params"]
    assert shown["pack"]["names"] is False
    import sqlite3

    with sqlite3.connect(sbox / "box.sqlite3") as conn:
        conn.execute("UPDATE policy_rule SET params = ? WHERE name = 'categories'", ('{"emotion": {"description": "", "multiple": true, "required": true}, "pack": {"description": "", "multiple": true, "required": false}}',))
    out = add_sticker(run_cli, sbox, tmp_path, 32, "--define", "emotion=开心", "高兴", "--define", "pack=MokaPackX", "a pack")
    assert any("pack=MokaPackX" in w for w in out["warnings"])


def test_merge_reports_aliases_dropped_at_the_cap(sbox, run_cli):
    box = ["--box", str(sbox)]
    run_cli("tag", "new", "emotion", "开心", "--means", "高兴", *box)
    run_cli("tag", "new", "emotion", "快乐", "--means", "高兴", *box)
    for i in range(20):
        run_cli("tag", "alias", "emotion", "开心", f"开心{i}", *box)
        run_cli("tag", "alias", "emotion", "快乐", f"快乐{i}", *box)
    out = run_cli("tag", "merge", "emotion", "快乐", "开心", *box)
    kept = [t for t in run_cli("tag", "list", "--category", "emotion", *box)["tags"] if t["value"] == "开心"][0]["aliases"]
    assert len(kept) == 32 and "快乐" in kept
    assert len(out["aliases_dropped"]) == 41 - 32
    assert not set(out["aliases_dropped"]) & set(kept)
    assert "dropped" in out["message"]
    small = run_cli("tag", "new", "emotion", "难过", "--means", "伤心", *box)
    assert small
    run_cli("tag", "new", "emotion", "伤心", "--means", "伤心", *box)
    assert run_cli("tag", "merge", "emotion", "伤心", "难过", *box)["aliases_dropped"] == []
