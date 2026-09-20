---
schema: clew/v1
id: course.mechanics.speed-from-a-graph
kind: section
title: "Speed from a distance-time graph"
summary: "Reading average speed as a slope, and instantaneous speed as a tangent."
course: "[[courses/mechanics/course]]"
parent: "[[courses/mechanics/chapters/motion]]"
previous: "[[courses/mechanics/sections/average-speed]]"
next: "[[courses/mechanics/sections/balanced-forces]]"
prerequisites:
  - "[[concepts/physics-average-speed]]"
source_refs:
  - "[[courses/mechanics/sources/mechanics-notes.pdf#page=2]]"
fidelity: verified
---

# Speed from a distance-time graph

<!-- clew:nav -->
Course: [[courses/mechanics/course|Mechanics of everyday motion]] · Chapter: [[courses/mechanics/chapters/motion|Describing motion]]
Previous: [[courses/mechanics/sections/average-speed|Average speed]] · Next: [[courses/mechanics/sections/balanced-forces|Balanced forces]]
Originals: [[courses/mechanics/sources/mechanics-notes.pdf#page=2|mechanics-notes.pdf, page 2]]
<!-- /clew:nav -->

A distance-time graph plots distance on the vertical axis against time on the
horizontal one. Reading [[concepts/physics-average-speed|average speed]] off it
is the same division as before, done geometrically.

Between two instants $t_1$ and $t_2$, the average speed is the slope of the
straight line joining the two points:

$$
\bar v = \frac{s(t_2) - s(t_1)}{t_2 - t_1}.
$$

A steeper line means a larger speed. A horizontal line means the distance is
not changing, so the object is at rest.

## From the average to the instant

Shrinking the interval around a single instant turns the chord into the tangent
at that point, and the average speed into the instantaneous speed:

```math
v(t) = \lim_{\Delta t \to 0} \frac{s(t + \Delta t) - s(t)}{\Delta t}
     = \frac{\mathrm{d}s}{\mathrm{d}t}.
```

The average over a whole journey is a single number. The tangent gives one
number per instant, which is why a graph says more than an average does.

## Reading it honestly

A distance-time graph records distance travelled, not position, so it never
decreases. A curve bending upwards means the speed is increasing; a curve
flattening out means it is decreasing.
