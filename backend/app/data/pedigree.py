"""Pedigree generation and relationship inference (section 7.1).

A pedigree is a small family tree (up to 5 generations) built from a founding couple. Only a
random subset of its members is later "registered" as donors, which is how a real registry looks:
you rarely have every relative, but you often have a few scattered ones.

Relationships are *derived* from the tree rather than hand-labelled. For two people x, y we find
their closest common ancestors, with dx / dy = generations from x / y up to that ancestor, then:

    expected shared DNA fraction = (number of shared ancestors, max 2) * (1/2) ** (dx + dy)

Checks against the usual textbook values:
    parent/child (0,1) 0.5 | full siblings (1,1) 2*0.25 = 0.5 | half siblings 0.25
    grandparent (0,2) 0.25 | aunt/uncle (1,2) 0.25 | first cousin (2,2) 0.125
    second cousin (3,3) 0.031 | third cousin (4,4) 0.0078 (about 0.8%)

IMPORTANT: these are *expected averages*. Real sharing varies, especially for distant cousins
(a third cousin may share nothing detectable). The exposure model built on top of this is a
simulation, not a forecast about any real database.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MAX_MEIOSES = 8  # third cousins are (4, 4) -> 8 meioses; farther pairs are ignored


@dataclass
class Person:
    pid: int
    gen: int
    sex: str  # "M" / "F"
    father: int | None = None
    mother: int | None = None


def build_pedigree(rng: np.random.Generator, max_depth: int = 4) -> list[Person]:
    """Founding couple at generation 0; each couple has 1-3 children; each child (except in the
    last generation) marries an unrelated founder. Parents always precede children in the list."""
    people: list[Person] = []

    def new(gen: int, sex: str, father=None, mother=None) -> Person:
        p = Person(len(people), gen, sex, father, mother)
        people.append(p)
        return p

    f0, m0 = new(0, "M"), new(0, "F")
    couples = [(f0.pid, m0.pid)]
    for gen in range(max_depth):
        next_couples = []
        for father, mother in couples:
            parent_pairs = [(father, mother)] * int(rng.choice([1, 2, 2, 3]))
            if rng.random() < 0.2:  # father has one child with a new partner -> half-sibling
                new_mother = new(people[father].gen, "F")
                parent_pairs.append((father, new_mother.pid))
            for f, m in parent_pairs:
                kid = new(gen + 1, "M" if rng.random() < 0.5 else "F", f, m)
                if gen + 1 < max_depth:
                    spouse = new(gen + 1, "F" if kid.sex == "M" else "M")
                    pair = (kid, spouse) if kid.sex == "M" else (spouse, kid)
                    next_couples.append((pair[0].pid, pair[1].pid))
        couples = next_couples
    return people


def _ancestor_distances(people: list[Person]) -> list[dict[int, int]]:
    """For each person: {ancestor_pid: generations up}, including themselves at distance 0."""
    out: list[dict[int, int]] = []
    for p in people:  # parents precede children, so out[parent] already exists
        d = {p.pid: 0}
        for parent in (p.father, p.mother):
            if parent is not None:
                for anc, dist in out[parent].items():
                    d[anc] = min(d.get(anc, 99), dist + 1)
        out.append(d)
    return out


def _ordinal(n: int) -> str:
    return {1: "first", 2: "second", 3: "third"}.get(n, f"{n}th")


def relation_name(dx: int, dy: int, n_shared: int) -> str:
    """Name of what person x (dx generations below the common ancestor) is to y. dx <= dy."""
    if dx == 0:
        return "parent" if dy == 1 else ("great-" * (dy - 2)) + "grandparent"
    if dx == 1 and dy == 1:
        return "sibling" if n_shared >= 2 else "half-sibling"
    if dx == 1:
        return ("great-" * (dy - 2)) + "aunt/uncle"
    base = f"{_ordinal(dx - 1)} cousin"
    return base if dx == dy else f"{base} {dy - dx}x removed"


def relate(anc_x: dict[int, int], anc_y: dict[int, int]) -> tuple[str, int, float] | None:
    """Relationship of the pair as (name, meioses, expected_shared_fraction), or None if unrelated
    or too distant. The name is from the point of view of the person with the SHORTER path."""
    common = [(a, anc_x[a], anc_y[a]) for a in anc_x.keys() & anc_y.keys()]
    if not common:
        return None
    best = min(dx + dy for _, dx, dy in common)
    if best > MAX_MEIOSES:
        return None
    top = [(dx, dy) for _, dx, dy in common if dx + dy == best]
    dx, dy = top[0]
    n_shared = min(len(top), 2)
    shared = n_shared * 0.5**best
    lo, hi = min(dx, dy), max(dx, dy)
    return relation_name(lo, hi, n_shared), best, shared


def pedigree_relationships(
    people: list[Person], registered: list[int]
) -> list[tuple[int, int, str, int, float]]:
    """All related pairs among the registered pids: (pid_a, pid_b, relation, meioses, shared).
    pid_a is the person with the shorter path to the common ancestor (the 'older' side)."""
    anc = _ancestor_distances(people)
    out = []
    for i, a in enumerate(registered):
        for b in registered[i + 1 :]:
            r = relate(anc[a], anc[b])
            if r is None:
                continue
            name, meioses, shared = r
            # orient so a is the one closer to the common ancestor
            if _path(anc[a], anc[b]) > _path(anc[b], anc[a]):
                a_, b_ = b, a
            else:
                a_, b_ = a, b
            out.append((a_, b_, name, meioses, shared))
    return out


def _path(anc_x: dict[int, int], anc_y: dict[int, int]) -> int:
    """x's generations up to the closest common ancestor with y."""
    common = anc_x.keys() & anc_y.keys()
    best = min(anc_x[a] + anc_y[a] for a in common)
    return min(anc_x[a] for a in common if anc_x[a] + anc_y[a] == best)


def kinship_matrix(people: list[Person]) -> np.ndarray:
    """Expected shared fraction between every pair of pedigree members (0 if unrelated/too far)."""
    anc = _ancestor_distances(people)
    n = len(people)
    k = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            r = relate(anc[i], anc[j])
            if r is not None:
                k[i, j] = k[j, i] = r[2]
    return k


def sample_registered(
    rng: np.random.Generator, people: list[Person], size: int, kin: np.ndarray
) -> list[int]:
    """Pick `size` members to register. After the first pick, closer relatives of people already
    chosen are more likely (weight 1 + 20 * kinship), so families contain a realistic mix of
    close and distant relatives rather than only scattered cousins."""
    size = min(size, len(people))
    chosen = [int(rng.integers(len(people)))]
    while len(chosen) < size:
        w = 1.0 + 20.0 * kin[chosen].sum(axis=0)
        w[chosen] = 0.0
        chosen.append(int(rng.choice(len(people), p=w / w.sum())))
    return sorted(chosen)
