"""Local features (SIFT) for crop, zoom and rotation duplicates. Filled in by M6."""


def stage(box, policy: dict, result, sidecar: dict) -> None:
    sidecar["sift_matches"] = []


def store(box, sha: str, sidecar: dict) -> None:
    pass
