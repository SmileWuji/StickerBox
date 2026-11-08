# SIFT tuning (2026-11-08)

`python3 scripts/sift_tuning.py` on the private corpora: 150 static stickers with at least 30
keypoints are stored; each gets five generated variants (crop of 45 to 70% per side upscaled
back, rotation of 12 to 40 degrees at 0.85 scale, half size, a white bar with text over the
bottom 30%, and the picture inside a fake chat screenshot with a dark header and text lines).
Every variant is matched against all 150 stored images through the full pipeline (vote,
shortlist of 3, ratio test 0.75, RANSAC). Numbers only.

## Verification model

A full homography (8 degrees of freedom) fitted clusters of look-alike strokes and produced 634
false matches, most labelled "rotation" with degenerate transforms. Every relation the box
reports is a similarity transform (rotation, uniform scale, translation), so verification fits
that (`cv2.estimateAffinePartial2D`) and requires the inliers to span at least 4% of both
pictures and the scale to be within 0.05 to 20. Pairwise, on random pairs, that separates well:
true matches have median inlier ratio 0.95 and spread 0.5 to 0.6; false ones have median spread 0
in the stored picture (collapsed transforms). With the checks, 548 of 600 true pairs pass at
12 inliers against 20 of 2,400 random pairs (0.8%).

## Full pipeline, min_inliers 12 (the new default)

| variant | found | median inliers | kind reported |
|---|---|---|---|
| crop | 116/150 | 40 | crop_of 113 |
| rotation | 150/150 | 175 | rotation 150 |
| half size | 149/150 | 111 | duplicate 149 |
| overlay | 147/150 | 208 | duplicate 147 |
| screenshot | 114/150 | 60 | contains 114 |

- 667 of 750 variants are linked to their original (89%).
- 122 extra relations to other stored images across the 750 queries. About 60% are to stickers
  of the same pack, which reuse the same drawing (often a real partial match); the rest, about
  6% of queries, are spurious. In the gallery preset relations are reported, never acted on, so
  a spurious one costs the agent a look, not an image.
- Missed crops are shortlisted correctly but verify below 12 inliers: a 300-keypoint original
  has few keypoints inside a small crop. `sift.keypoints` 500 would help at about 1.7x storage.
- Insert time with 2,997 stored feature sets: median 1.7 s, max 3.5 s per match (one core for
  the BLAS product, 12-core host).

Sticker art is flat and repetitive, so this corpus is a pessimistic proxy for a chat gallery
of photos and screenshots. Re-measure on real gallery images once the owner has some.
