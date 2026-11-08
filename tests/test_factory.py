import numpy as np
from PIL import Image

import factory


def test_pictures_are_deterministic_and_distinct():
    assert np.array_equal(factory.picture(1), factory.picture(1))
    assert not np.array_equal(factory.picture(1), factory.picture(2))


def test_writers_produce_readable_files(tmp_path):
    rgba = factory.picture(3, (300, 200), alpha=True)
    frames = factory.animation(4, n=6, size=(128, 96))
    for path in [
        factory.write_png(tmp_path / "a.png", rgba),
        factory.write_jpg(tmp_path / "a.jpg", rgba),
        factory.write_webp(tmp_path / "a.webp", rgba),
    ]:
        with Image.open(path) as im:
            assert im.size == (300, 200)
    with Image.open(factory.write_animated_webp(tmp_path / "b.webp", frames)) as im:
        assert im.n_frames == 6
    with Image.open(factory.write_gif(tmp_path / "b.gif", frames)) as im:
        assert im.n_frames == 6
    assert factory.write_webm(tmp_path / "b.webm", frames).stat().st_size > 0
