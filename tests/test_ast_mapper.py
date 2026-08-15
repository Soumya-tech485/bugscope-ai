from app.services.ast_mapper import parse_python_source


def test_parse_function():
    source = """
def add(a, b):
    return a + b
"""

    entities = parse_python_source(source, "sample.py")

    names = [entity.name for entity in entities]

    assert "add" in names


def test_parse_class_and_method():
    source = """
class Calculator:
    def multiply(self, a, b):
        return a * b
"""

    entities = parse_python_source(source, "sample.py")

    names = [entity.name for entity in entities]

    assert "Calculator" in names
    assert "Calculator.multiply" in names
    