#!/usr/bin/env python3
"""Compare coverage table data from original and unextended patched genhtml."""

import argparse
from collections import Counter
import re
from pathlib import Path

ROW_PATTERN = re.compile(r"<tr\b[^>]*>.*?</tr>", re.I | re.S)


def normalize(page: Path) -> str:
    # The original and patched report are generated in separate processes.
    text = page.read_text(encoding="utf-8")
    text = re.sub(
        r"(<td\b[^>]*>\s*(?:Test\s+)?Date:\s*</td>\s*<td\b[^>]*>).*?(</td>)",
        r"\1DATE\2",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(r"<!--\s*Generated.*?-->", "", text, flags=re.I | re.S)
    return text


def rows(text: str) -> list[str]:
    def visible(row: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", row)).strip()

    return [visible(row) for row in ROW_PATTERN.findall(text)]


def compare(original: Path, patched: Path) -> None:
    left = {str(p.relative_to(original)): p for p in original.rglob("*.html")}
    right = {str(p.relative_to(patched)): p for p in patched.rglob("*.html")}
    if not left:
        raise AssertionError(f"No HTML pages found in {original}")
    if left.keys() != right.keys():
        missing = sorted(left.keys() - right.keys())
        unexpected = sorted(right.keys() - left.keys())
        raise AssertionError(f"Different HTML pages: missing={missing}, unexpected={unexpected}")

    reordered = 0
    metadata_differences = 0
    for name in sorted(left):
        a = normalize(left[name])
        b = normalize(right[name])
        if a == b:
            continue

        a_rows, b_rows = rows(a), rows(b)
        missing = Counter(a_rows) - Counter(b_rows)
        unexpected = Counter(b_rows) - Counter(a_rows)
        if missing or unexpected:
            details = []
            for label, counter in (("only original", missing), ("only patched", unexpected)):
                for value, count in list(counter.items())[:3]:
                    details.append(f"{label} ({count}x): {value[:220]}")
            raise AssertionError(
                f"Different HTML coverage table rows on page {name}:\n" + "\n".join(details)
            )
        if a_rows != b_rows:
            reordered += 1
        else:
            metadata_differences += 1

    print(
        f"Compatibility OK: {len(left)} pages have identical coverage table data "
        f"({reordered} with row order differences, "
        f"{metadata_differences} with non-table HTML differences)"
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("original", type=Path)
    p.add_argument("patched", type=Path)
    args = p.parse_args()
    compare(args.original, args.patched)


if __name__ == "__main__":
    main()
