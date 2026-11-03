"""Turns the generated refunds_combined.html into a page ready for the Artifact tool.

Keeps the <title>, <style> and <body> content (the Artifact tool adds its own
document wrapper), adds the light/dark theme guards the Artifact page expects,
and right-aligns digits in the table.

Usage: python scripts/make_artifact.py refunds_combined.html OUT.html
"""

import re
import sys


def make_artifact(html):
    title = re.search(r"<title>.*?</title>", html, re.S)
    style = re.search(r"<style>(.*?)</style>", html, re.S)
    body = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
    if not (title and style and body):
        raise ValueError("refunds_combined.html is missing its <title>, <style> or <body>")

    css = style.group(1)
    dark = re.search(
        r"@media \(prefers-color-scheme: dark\) \{\s*:root(?::not\(\[data-theme=\"light\"\]\))? \{(.*?)\}\s*\}",
        css,
        re.S,
    )
    if not dark:
        raise ValueError("couldn't find the dark-mode :root block in the dashboard CSS")
    dark_vars = dark.group(1)
    guarded = (
        "@media (prefers-color-scheme: dark) {\n"
        '    :root:not([data-theme="light"]) {' + dark_vars + "}\n  }"
    )
    css = css[: dark.start()] + guarded + css[dark.end():]
    if ':root[data-theme="dark"]' not in css:
        css = css.replace(guarded, guarded + '\n  :root[data-theme="dark"] {' + dark_vars + "}", 1)

    def tabular(m):
        rule = m.group(0)
        if "tabular-nums" in rule:
            return rule
        return rule[:-1].rstrip() + " font-variant-numeric: tabular-nums; }"

    css = re.sub(r"tbody td \{[^}]*\}", tabular, css, count=1)

    return f"{title.group(0)}\n<style>{css}</style>\n{body.group(1).strip()}\n"


def main():
    src, out = sys.argv[1], sys.argv[2]
    with open(src) as f:
        page = make_artifact(f.read())
    with open(out, "w") as f:
        f.write(page)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
