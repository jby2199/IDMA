from app.core.entities import AIResult, ArtifactEntry, ClassificationResult, Knowledge
from app.core.rule_engine import ClassificationService


class SpyAI:
    def __init__(self, result=None):
        self.called = 0
        self.result = result

    def classify(self, filename: str, knowledge: Knowledge):
        _ = (filename, knowledge)
        self.called += 1
        return self.result


class StubProjectDocClassifier:
    def __init__(self, result=None):
        self.result = result
        self.called = 0

    def classify(self, filename: str, knowledge: Knowledge):
        _ = (filename, knowledge)
        self.called += 1
        return self.result


def _knowledge() -> Knowledge:
    return Knowledge(
        phases=("Design", "Implementation"),
        artifacts=(
            ArtifactEntry(phase="Design", abbr="SDD", full_name="Software Design Description"),
            ArtifactEntry(phase="Implementation", abbr="STP", full_name="System Test Procedure"),
            ArtifactEntry(phase="Implementation", abbr="CTP", full_name="Component Test Procedure"),
        ),
    )


def test_abbr_match_skips_ai() -> None:
    ai = SpyAI()
    service = ClassificationService(ai)

    result = service.classify("ABC_SDD_v1.pdf", _knowledge(), 0.5, 0.8)

    assert result.method == "Rule-ABBR"
    assert result.artifact_abbr == "SDD"
    assert ai.called == 0


def test_full_name_ratio_match() -> None:
    ai = SpyAI()
    service = ClassificationService(ai)

    result = service.classify("software-design-v2.pdf", _knowledge(), 0.5, 0.8)

    assert result.method == "Rule-FULL"
    assert result.artifact_abbr == "SDD"


def test_ambiguous_triggers_ai() -> None:
    ai = SpyAI(AIResult(artifact_abbr="CTP", phase="Implementation", ai_confidence=0.9))
    service = ClassificationService(ai)

    result = service.classify("test procedure.pdf", _knowledge(), 0.5, 0.8)

    assert ai.called == 1
    assert result.method == "AI"
    assert result.artifact_abbr == "CTP"


def test_project_doc_classifier_takes_priority() -> None:
    ai = SpyAI()
    project_doc = StubProjectDocClassifier(
        ClassificationResult(
            phase="Implementation",
            artifact_abbr="STP",
            method="Rule-ABBR",
            confidence=1.0,
            reason="doc-list",
        )
    )
    service = ClassificationService(ai, project_doc_classifier=project_doc)

    result = service.classify("anything.pdf", _knowledge(), 0.5, 0.8)

    assert project_doc.called == 1
    assert ai.called == 0
    assert result.artifact_abbr == "STP"
