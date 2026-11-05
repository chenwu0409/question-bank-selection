"""Flag action overlap beyond task-mandated actions. This does not reject candidates."""
import argparse
import json
from pathlib import Path


def compare(candidate, prior, mandatory, threshold=0.75):
    if not 0 < threshold <= 1:
        raise ValueError("threshold must be in (0, 1]")
    left, right = set(candidate) - set(mandatory), set(prior) - set(mandatory)
    similarity = len(left & right) / len(left | right) if left and right else None
    return {"similarity": similarity, "suspected_duplicate": similarity is not None and similarity >= threshold}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(**json.loads(args.snapshot.read_text(encoding="utf-8")))))
