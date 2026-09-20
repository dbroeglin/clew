---
schema: clew/v1
id: course.proportional-reasoning.scaling-a-recipe
kind: section
title: "Scaling a recipe"
summary: "Using one scale factor for every quantity, and checking the result."
course: "[[courses/proportional-reasoning/course]]"
parent: "[[courses/proportional-reasoning/chapters/ratios]]"
previous: "[[courses/proportional-reasoning/sections/reading-a-ratio]]"
next: null
prerequisites:
  - "[[concepts/math-ratios]]"
source_refs:
  - "[[courses/proportional-reasoning/sources/proportional-reasoning-notes.pdf#page=2]]"
fidelity: verified
---

# Scaling a recipe

<!-- clew:nav -->
Course: [[courses/proportional-reasoning/course|Proportional reasoning]] · Chapter: [[courses/proportional-reasoning/chapters/ratios|Ratios]]
Previous: [[courses/proportional-reasoning/sections/reading-a-ratio|Reading a ratio]] · Next: none
Originals: [[courses/proportional-reasoning/sources/proportional-reasoning-notes.pdf#page=2|proportional-reasoning-notes.pdf, page 2]]
<!-- /clew:nav -->

Rescaling a recipe means changing every quantity while keeping every
[[concepts/math-ratios|ratio]] the same. One scale factor does the whole job.

To go from a recipe serving $n$ people to one serving $m$, the scale factor is

$$
k = \frac{m}{n},
$$

and every quantity $q$ becomes $kq$.

## Worked example

A recipe for $4$ people uses $200\ \mathrm{g}$ of flour and $100\ \mathrm{ml}$
of milk. For $6$ people, $k = 6/4 = 1.5$, giving $300\ \mathrm{g}$ of flour and
$150\ \mathrm{ml}$ of milk.

The flour-to-milk ratio is still $2$, as it must be: both quantities were
multiplied by the same $k$.

## The usual mistake

Adding a fixed amount to each quantity instead of multiplying does not preserve
the ratio. Adding $100$ to both gives $300 : 200$, a ratio of $1.5$ rather than
$2$, so the result is a different recipe.

A quick check is to rescale, then recompute one ratio. If it moved, the scaling
was additive somewhere.
