from decimal import Decimal
from packages.model_monitoring import ModelSurveillanceEngine, SurveillanceLimits

def test_surveillance_requires_consecutive_breaches_before_retirement():
    engine=ModelSurveillanceEngine(limits=SurveillanceLimits(max_psi=Decimal("0.2"),max_consecutive_breaches=3))
    one=engine.observe(model_id="m",version="1",psi=Decimal("0.4"))
    two=engine.observe(model_id="m",version="1",psi=Decimal("0.5"))
    three=engine.observe(model_id="m",version="1",psi=Decimal("0.6"))
    assert one.decision=="RETAIN" and two.breach_count==2 and three.decision=="RETIRE"
    assert three.breach_count==3

def test_clean_observation_resets_breach_streak():
    engine=ModelSurveillanceEngine(limits=SurveillanceLimits(max_consecutive_breaches=2))
    engine.observe(model_id="m",version="1",psi=Decimal("0.4"))
    clean=engine.observe(model_id="m",version="1",psi=Decimal("0.1"))
    assert clean.breach_count==0 and clean.decision=="RETAIN"
