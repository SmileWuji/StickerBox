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


def test_query_option_takes_text_starting_with_a_dash(tagged):
    root, refs, cli = tagged
    result = cli("search", "--query=-_-", "--box", str(root))
    assert result["query"] == "-_-"
    assert top(tagged, "--query=-_- 卖惨") == [4]
    assert top(tagged, "无语", "--query=托腮")[0] == 2


def test_seed_needs_random(tagged):
    root, refs, cli = tagged
    from sticker_box.cli import main

    assert main(["--json", "search", "--seed", "3", "--box", str(root)]) == 2


def test_random_shuffles_only_equal_scores(tagged):
    root, refs, cli = tagged
    newest = top(tagged, "--tag", "emotion=开心", n=10)
    orders = {tuple(top(tagged, n=12, extra=("--random", "--seed", str(seed)))) for seed in range(8)}
    assert len(orders) > 1
    assert all(sorted(order) == sorted(refs) for order in orders)
    assert top(tagged, n=12, extra=("--random", "--seed", "3")) == top(tagged, n=12, extra=("--random", "--seed", "3"))
    assert sorted(newest) == [5, 9]
    for seed in range(8):
        ranked = top(tagged, "无语", "托腮", n=3, extra=("--random", "--seed", str(seed)))
        assert ranked[0] == 2 and set(ranked[1:]) == {1, 12}


def test_chat_phrases_match_descriptions_by_shared_character_pairs(tmp_path, run_cli):
    root = tmp_path / "p"
    run_cli("init", str(root), "--preset", "telegram-sticker", "--language", "zh-Hans")
    refs = {}
    for seed, description in [(1, "抱着枕头睡着了"), (2, "举着牌子生气"), (3, "坐在电脑前打字")]:
        path = factory.write_webp(tmp_path / f"{seed}.webp", factory.picture(seed + 300, (512, 512), alpha=True))
        (staged,) = run_cli("stage", str(path), "--box", str(root))["results"]
        out = run_cli("commit", staged["ref"], "--box", str(root), "--license", "unknown", "--text", "", "--note", "测试",
                      "--description", description, "--define", "emotion=平静", "平静")
        refs[out["ref"]] = seed

    def found(query):
        return [refs[r["ref"]] for r in run_cli("search", f"--query={query}", "--box", str(root))["results"]]

    assert found("昨天抱着枕头就睡着了") == [1]
    assert found("笑死，他举着牌子") == [2]
    assert found("你怎么不会这个") == []
    assert found("枕头好软") == []
    assert found("睡着吗") == []


def test_a_phrase_match_ranks_below_the_exact_text(tmp_path, run_cli, monkeypatch):
    from sticker_box import clock

    root = tmp_path / "p"
    run_cli("init", str(root), "--preset", "telegram-sticker", "--language", "zh-Hans")
    refs = {}
    for seed, description in [(1, "抱枕头"), (2, "抱枕和枕头")]:
        monkeypatch.setattr(clock, "stamp", lambda seed=seed: f"2026-01-0{seed}T00:00:00Z")
        path = factory.write_webp(tmp_path / f"{seed}.webp", factory.picture(seed + 400, (512, 512), alpha=True))
        (staged,) = run_cli("stage", str(path), "--box", str(root))["results"]
        out = run_cli("commit", staged["ref"], "--box", str(root), "--license", "unknown", "--text", "", "--note", "测试",
                      "--description", description, "--define", "emotion=平静", "平静")
        refs[out["ref"]] = seed
    results = run_cli("search", "抱枕头", "--box", str(root))["results"]
    assert [refs[r["ref"]] for r in results] == [1, 2]
    assert results[1]["score"] < results[0]["score"]
