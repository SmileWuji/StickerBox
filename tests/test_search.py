import pytest

import factory

STICKERS = [
    # seed, tags (defined on first use), text, note
    (1, ["emotion=无语"], "", "群友问了个蠢问题"),
    (2, ["emotion=无语", "visual=托腮"], "我想了零点一秒", "嫌对方问题太简单"),
    (3, ["emotion=嫌弃"], "", "看不上对方的操作"),
    (4, ["emotion=大哭"], "我会继续加油的", "被催进度时卖惨"),
    (5, ["emotion=开心", "visual=吃饭"], "饭点到了开饭啦", "话题聊死了的时候"),
    (6, ["emotion=生气"], "工资翻倍再说", "被要求加班"),
    (7, ["emotion=害羞"], "", "被夸的时候"),
    (8, ["emotion=震惊", "visual=张嘴"], "哇哦", "看到离谱消息"),
    (9, ["emotion=开心"], "", "收到礼物"),
    (10, ["emotion=哭"], "", "难过的时候"),
    (11, ["emotion=得意"], "我是最强的", "炫耀的时候"),
    (12, ["emotion=无语", "pack=测试包"], "", "无话可说"),
]
DEFINITIONS = {"无语": "说不出话的无奈", "嫌弃": "看不上", "大哭": "哭得很厉害", "开心": "高兴", "生气": "发火", "害羞": "不好意思",
               "震惊": "吓一跳", "哭": "流泪", "得意": "自鸣得意", "托腮": "手撑着下巴", "吃饭": "在吃东西", "张嘴": "嘴巴张开",
               "测试包": "测试用的包"}


@pytest.fixture(scope="module")
def tagged(tmp_path_factory):
    import json

    from sticker_box.cli import main

    def cli(*argv):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["--json", *argv])
        assert code == 0, buf.getvalue()
        return json.loads(buf.getvalue())

    tmp = tmp_path_factory.mktemp("search")
    root = tmp / "s"
    box = ["--box", str(root)]
    cli("init", str(root), "--preset", "telegram-sticker", "--language", "zh-Hans")
    cli("tag", "new", "emotion", "负面", "--means", "不好的情绪", *box)
    defined, refs = set(), {}
    for seed, tags, text, note in STICKERS:
        if "emotion=嫌弃" in tags and "嫌弃" not in defined:
            cli("tag", "new", "emotion", "嫌弃", "--means", DEFINITIONS["嫌弃"], "--parent", "负面", "--alias", "鄙视", *box)
            defined.add("嫌弃")
        if "emotion=生气" in tags and "生气" not in defined:
            cli("tag", "new", "emotion", "生气", "--means", DEFINITIONS["生气"], "--parent", "负面", *box)
            defined.add("生气")
        path = factory.write_webp(tmp / f"{seed}.webp", factory.picture(seed + 100, (512, 512), alpha=True))
        (staged,) = cli("stage", str(path), *box)["results"]
        args = []
        for tag in tags:
            value = tag.split("=", 1)[1]
            if value in defined:
                args += ["--tag", tag]
            else:
                args += ["--define", tag, DEFINITIONS[value]]
                defined.add(value)
        out = cli("commit", staged["ref"], *box, "--license", "unknown", "--text", text, "--note", note, *args)
        refs[seed] = out["ref"]
    return root, refs, cli


def top(tagged, *query, n=5, extra=()):
    root, refs, cli = tagged
    seed_of = {v: k for k, v in refs.items()}
    result = cli("search", *query, "--box", str(root), "--limit", str(n), *extra)
    return [seed_of[r["ref"]] for r in result["results"]]


@pytest.mark.parametrize("query, first, contains", [
    (["无语"], {1, 2, 12}, set()),                 # two-character tag
    (["鄙视"], {3}, set()),                         # alias
    (["负面"], {3, 6}, set()),                      # broader tag reaches narrower ones
    (["哭"], {10}, {4}),                            # exact tag first, longer tag containing it next
    (["吃饭"], {5}, set()),                         # visual tag and on-image text agree
    (["工资"], {6}, set()),                         # on-image text only
    (["卖惨"], {4}, set()),                         # note only
    (["开心|震惊"], {5, 9, 8}, set()),              # either term
    (["emotion=开心"], {5, 9}, set()),              # one exact tag
    (["无语", "托腮"], {2}, {1, 12}),               # both terms beat one
])
def test_ten_realistic_queries(tagged, query, first, contains):
    got = top(tagged, *query)
    assert set(got[: len(first)]) == first, got
    assert contains <= set(got), got


def test_filters(tagged):
    assert top(tagged, extra=("--tag", "pack=测试包")) == [12]
    assert set(top(tagged, "无语", extra=("--tag", "visual=托腮"))) == {2}
    assert top(tagged, "无语", extra=("--animated",)) == []
    assert len(top(tagged, n=20)) == 12


def test_unknown_filter_tag_suggests(tagged):
    root, _, cli = tagged
    out = cli("search", "--tag", "emotion=无言", "--box", str(root))
    assert out["results"] == [] and out["suggestions"] == ["emotion=无语"]


def test_like_wildcards_are_literal(tagged):
    assert top(tagged, "%") == [] and top(tagged, "_") == []


def test_empty_text_stays_empty_and_definitions_are_searched(tagged):
    root, refs, cli = tagged
    results = {r["ref"]: r for r in cli("search", "--box", str(root), "--limit", "20")["results"]}
    assert results[refs[1]]["text"] == ""
    assert 3 in top(tagged, "鄙视") and 1 in top(tagged, "说不出话")
