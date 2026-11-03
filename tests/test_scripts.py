import importlib.util
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_make_artifact_adds_theme_guards_and_tabular_nums(tmp_path):
    import pandas as pd

    from actblue_refunds.dashboard import write_dashboard

    src = tmp_path / "d.html"
    df = pd.DataFrame([{"account": "A", "Refund ID": "1", "Refund Amount": 10.0, "Refund Date": "2026-10-01"}])
    write_dashboard(df, str(src), start="2026-05-01", end="2026-11-01")

    page = _load("make_artifact").make_artifact(src.read_text())

    assert "<html" not in page and "<body" not in page and "<!doctype" not in page.lower()
    assert page.startswith("<title>")
    assert ':root:not([data-theme="light"])' in page
    assert ':root[data-theme="dark"]' in page
    assert "font-variant-numeric: tabular-nums" in page
    assert "const DATA = " in page
    # Running it on its own output again doesn't duplicate anything.
    again = _load("make_artifact").make_artifact(f"<title>t</title><style>{page.split('<style>')[1].split('</style>')[0]}</style><body>x</body>")
    assert again.count(':root[data-theme="dark"]') == 1
    tbody_rule = again.split("tbody td {")[1].split("}")[0]
    assert tbody_rule.count("tabular-nums") == 1


def test_email_body_stacked_format():
    build = _load("email_body").build
    out = build(
        {
            "bootstrapped": False,
            "new_refunds": [
                {"account": "Donavan McKinney", "amount": 10.0, "refund_date": "2026-10-31 09:00:00", "form": "rtext",
                 "donor_first_name": "Kate", "donor_last_name": "Blain"},
                {"account": "Brad Lander", "amount": 3.0, "refund_date": "2026-10-31", "form": "email",
                 "donor_first_name": "Muse", "donor_last_name": "Bedri"},
            ],
        },
        "https://claude.ai/artifact/x",
    )
    assert out["send"] is True
    assert out["subject"] == "2 new ActBlue refund(s)"
    assert out["body"] == (
        "Brad Lander\n$3.00 · 2026-10-31 · form: email\nDonor: Muse Bedri\n\n"
        "Donavan McKinney\n$10.00 · 2026-10-31 · form: rtext\nDonor: Kate Blain\n\n"
        "Dashboard: https://claude.ai/artifact/x"
    )


def test_email_body_nothing_to_send_on_baseline_or_empty():
    build = _load("email_body").build
    assert build({"bootstrapped": True, "new_refunds": [{"account": "A"}]}, "u")["send"] is False
    assert build({"bootstrapped": False, "new_refunds": []}, "u")["send"] is False
