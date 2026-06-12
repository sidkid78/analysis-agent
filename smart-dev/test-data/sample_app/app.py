"""A tiny sample app with intentional issues for the analyzer to find."""

import os

API_KEY = "sk_live_abcdef1234567890"  # hardcoded credential (intentional)


def process(items, mode, retries, verbose, strict, dry_run):
    """An overly long, branchy function (intentional complexity)."""
    results = []
    for it in items:
        if mode == "a":
            if it > 0:
                results.append(it * 2)
            elif it < 0:
                results.append(-it)
            else:
                results.append(0)
        elif mode == "b":
            for r in range(retries):
                if verbose and r > 0:
                    print("retrying", r)  # debug statement (intentional)
                if it % 2 == 0 and strict:
                    results.append(it)
                elif it % 2 == 1 or not strict:
                    results.append(it + 1)
        else:
            try:
                results.append(1 / it)
            except:  # bare except (intentional)
                pass
    # TODO: handle dry_run properly
    return results


def main():
    print(process([1, -2, 3, 0], "a", 2, True, False, False))


if __name__ == "__main__":
    main()
