from pathlib import Path

from rac.storage import YamlStorageAdapter

SAMPLE = Path(__file__).parent.parent / "examples" / "sample_resume.yaml"


def test_load_sample_resume():
    doc = YamlStorageAdapter().load(SAMPLE)
    assert doc.person.name == "Jamie Rivera"
    assert len(doc.positions) == 2
    assert len(doc.claims) == 3


def test_round_trip(tmp_path):
    doc = YamlStorageAdapter().load(SAMPLE)
    out = tmp_path / "roundtrip.yaml"
    YamlStorageAdapter().save(doc, out)
    reloaded = YamlStorageAdapter().load(out)
    assert reloaded == doc
