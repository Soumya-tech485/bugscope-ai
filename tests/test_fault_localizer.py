from app.services.ast_mapper import parse_repo
from app.services.fault_localizer import localize


def test_traceback_localization(tmp_path):
    file_path = tmp_path / "app.py"

    file_path.write_text(
        """
def boom():
    return 1 / 0
"""
    )

    code_map = parse_repo(tmp_path)

    trace = """
Traceback (most recent call last):
  File "app.py", line 3, in boom
    return 1 / 0
ZeroDivisionError: division by zero
"""

    suspects = localize(
        code_map=code_map,
        bug_report="boom crashes",
        error_trace=trace,
        top_n=5,
    )

    assert suspects
    assert suspects[0].name == "boom" 