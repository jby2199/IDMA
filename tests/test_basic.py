"""Basic tests for the template project."""

from app.core.logic import add
from app.models.model_example import ModelExample


def test_add(): # Basic test for the add function
    assert add(2, 3) == 5


def test_model_dataclass():
    m = ModelExample(id=1, name="alice")
    assert m.id == 1 and m.name == "alice"
