---
schema_version: 1
id: sequences-demo-aid-ex2-1
type: help
question: "[[sequences-demo-exercise-2#^q-ex2-1]]"
correction: "[[sequences-demo-correction-2#^r-ex2-1]]"
---

> [!hint]
> Start from $1\leq v_n\leq 3$ and bound $(v_n+3)/2$ to
> prepare the [[sequences-demo-course#Monotone convergence|induction step]].

^hint-1

> [!hint]
> Calculate $v_{n+1}-v_n$ and use the upper bound, as
> suggested by the [[sequences-demo-course#Monotone convergence|course method]].

^hint-2

> [!explanation]
> The bound holds at index $0$. If it holds at index $n$,
> then $2\leq (v_n+3)/2\leq 3$, which establishes the induction step.
> The displayed difference is nonnegative because $v_n\leq 3$:
> this uses the [[sequences-demo-course#Monotone convergence|monotonicity criterion]].

^explanation-1
