---
name: tag-emotion
description: Choose the emotion tags of a sticker, the feeling or reaction it expresses. Use for every sticker added to a box with an emotion category.
---

# Emotion

The `emotion` category answers: what would I be saying, feeling or doing if I sent this? It is
the main way a sticker gets found mid-conversation, so tag the reaction, not the drawing.

## How to decide

- Read the text first, then the face and the pose. When there is text, it usually decides: a
  smiling face captioned "谢谢你啊" after a mishap is sarcasm, not happiness.
- Start from the emotion tags in the box's `README.md`: read each definition and take every
  tag whose definition fits. Create a new tag only when none fits and the vocabulary is open.
- One to three tags. Add a second only when it is also clearly there (embarrassed and happy;
  angry and helpless). Order does not matter.
- Prefer the words people would type when looking for a reply: 无语, 嫌弃, 委屈, 得意, 震惊,
  开心, 生气, 害羞, 卖萌, 疑惑, 摆烂, 求饶. Reuse what the box already has.
- A sticker made to be funny (a joke, an absurd face, a pun) also gets the box's tag for
  humour when it has one: that is how people look for it.
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
