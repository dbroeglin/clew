---
title: Mathematics in Markdown
previous: "[[courses/reader-tour/hub|Course home]]"
next: "[[02-session-actions|Working with the session]]"
---

# Mathematics in Markdown

KaTeX renders inline formulas such as $a^2 + b^2 = c^2$ within the text.

## Display equations

For a longer expression, use a display block:

$$
\int_0^1 x^2\,dx = \left[\frac{x^3}{3}\right]_0^1 = \frac{1}{3}.
$$

Math fences work too:

```math
\begin{pmatrix}
a & b \\
c & d
\end{pmatrix}
\begin{pmatrix}
x \\
y
\end{pmatrix}
=
\begin{pmatrix}
ax+by \\
cx+dy
\end{pmatrix}.
```

## Literal source

Inline code stays literal: `$a^2 + b^2 = c^2$`.

The formulas, fonts, and styles are rendered locally. To discuss the integral,
select a passage and choose **Ask in chat**, then write and send your question
in the chat composer.
