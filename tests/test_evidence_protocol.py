from packages.evidence_protocol import EvidenceClass,EvidencePack,EvidenceStatus

def test_gate_fails_closed_on_unobserved():
    p=EvidencePack.create(commit_sha="x"); p.add(name="live",evidence_class=EvidenceClass.LIVE_DEMO,status=EvidenceStatus.UNOBSERVED)
    assert p.gate_status()==EvidenceStatus.UNOBSERVED

def test_gate_fails_on_required_failure():
    p=EvidencePack.create(commit_sha="x"); p.add(name="a",evidence_class=EvidenceClass.LIVE_DEMO,status=EvidenceStatus.PASS); p.add(name="b",evidence_class=EvidenceClass.LIVE_DEMO,status=EvidenceStatus.FAIL)
    assert p.gate_status()==EvidenceStatus.FAIL
