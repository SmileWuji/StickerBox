---
name: tag-emotion
description: Choose the emotion tags of a sticker, the feeling or reaction it expresses. Use for every sticker added to a box with an emotion category.
---

# Emotion

The `emotion` category answers: what would I be saying, feeling or doing if I sent this? It is
the main way a sticker gets found mid-conversation, so tag the reaction, not the drawing.

## How to decide

- Look at the face, the pose and the text together. Text often decides it: a smiling face
  captioned "谢谢你啊" after a mishap is sarcasm, not happiness.
- One to three tags. The main reaction first; add a second only when it is also clearly there
  (embarrassed and happy; angry and helpless).
- Prefer the words people would type when looking for a reply: 无语, 嫌弃, 委屈, 得意, 震惊,
  开心, 生气, 害羞, 卖萌, 疑惑, 摆烂, 求饶. Reuse what the box already has.
- Broader and narrower feelings can be linked with `tag parent` (负面 > 嫌弃) during cleanup;
  tag the narrow one.

## Avoid

- Describing the art instead of the feeling ("smiling", "big eyes": those belong to `visual`).
- Guessing a feeling the sticker does not show. A blank face holding a sign is about the sign.
- Near-twins of an existing tag (无语 and 无语了, 开心 and 高兴): use the existing one, or
  propose a merge in the cleanup pass.

## Examples

- A character slumped on a desk, caption "不想上班" → `emotion=摆烂`, maybe `emotion=疲惫`
- Rolling eyes with arms crossed → `emotion=嫌弃`
- Teary eyes, hands together, caption "求求了" → `emotion=求饶`
