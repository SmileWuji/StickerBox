"""Starting policies. A preset is only a starting point; `sticker-box policy set` changes any rule.

Telegram numbers: https://core.telegram.org/stickers and the Bot API, read 2026-11-08. Static
stickers are WEBP or PNG with one side exactly 512 px and the other at most 512 px; the current
docs give no size limit for them, so the 512 KB cap here is this tool's conservative choice.
Video stickers are WEBM VP9, one side 512 px, at most 3 s, 30 fps and 256 KB, with no audio."""

import copy

_STATIC_512 = {"animated": False, "one_side": 512, "max_side": 512, "max_bytes": 512 * 1024}

PRESETS = {
    "telegram-sticker": {
        "description": "Telegram-style stickers: static WEBP or PNG, and VP9 WEBM video, one side exactly 512 px. Convert files before adding them; the box only checks.",
        "policy": {
            "fields": {
                "text": {"required": True, "allow_empty": True, "description": "Every piece of text on the image, verbatim, watermarks included; empty when there is none."},
                "note": {"required": True, "description": "When to send it."},
                "license": {"required": True, "description": "Licence of the image; 'unknown' when it cannot be found out."},
                "description": {"description": "What the image shows."},
                "source": {"description": "Where the image came from, such as a pack link."},
            },
            "categories": {
                "emotion": {"description": "The feeling or reaction the sticker expresses.", "multiple": True, "required": True},
                "character": {"description": "Who is pictured, named after the box's reference sources.", "multiple": True},
                "series": {"description": "The work or franchise the character comes from.", "multiple": True},
                "visual": {"description": "What is shown: actions, objects, poses, notable details.", "multiple": True},
                "pack": {"description": "A collection the sticker belongs to; a pack is a tag.", "multiple": True},
            },
            "files": {
                "formats": {
                    "webp": copy.deepcopy(_STATIC_512),
                    "webm": {"codecs": ["vp9"], "audio": False, "one_side": 512, "max_side": 512, "max_bytes": 256 * 1024, "max_duration_ms": 3000, "max_fps": 30},
                    "png": copy.deepcopy(_STATIC_512),
                },
                "all": {},
            },
            "vocabulary": {"mode": "open", "default_category": None},
            "duplicates": {"phash_max_distance": 6, "sift": None, "on_duplicate": "reject"},
            "limits": {"max_bytes": None, "max_items": None},
            "retention": {"expire_after_minutes": None, "staged_grace_minutes": 60},
            "analysis": {"ocr_hint": True},
        },
    },
    "gallery": {
        "description": "A gallery of images kept at their original size, with free-form tags.",
        "policy": {
            "fields": {"license": {"required": True, "description": "Licence of the image; 'unknown' when it cannot be found out."}},
            "categories": {"tag": {"description": "Free-form tags.", "multiple": True}},
            "files": {"formats": None, "all": {}},
            "vocabulary": {"mode": "free", "default_category": "tag"},
            "duplicates": {"phash_max_distance": 6, "sift": {"keypoints": 300, "min_inliers": 12, "ratio": 0.75}, "on_duplicate": "report"},
            "limits": {"max_bytes": None, "max_items": None},
            "retention": {"expire_after_minutes": None, "staged_grace_minutes": 60},
            "analysis": {"ocr_hint": False},
        },
    },
    "buffer": {
        "description": "A short-lived buffer: images expire 60 minutes after they are added.",
        "policy": {
            "fields": {"license": {"required": True, "description": "Licence of the image; 'unknown' when it cannot be found out."}},
            "categories": {"tag": {"description": "Free-form tags.", "multiple": True}},
            "files": {"formats": None, "all": {}},
            "vocabulary": {"mode": "free", "default_category": "tag"},
            "duplicates": {"phash_max_distance": 6, "sift": None, "on_duplicate": "link"},
            "limits": {"max_bytes": None, "max_items": None},
            "retention": {"expire_after_minutes": 60, "staged_grace_minutes": 60},
            "analysis": {"ocr_hint": False},
        },
    },
}


def get(name: str) -> dict:
    return copy.deepcopy(PRESETS[name])
