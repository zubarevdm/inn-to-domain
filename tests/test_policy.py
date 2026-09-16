"""Тесты политики ответа.

Сеть не нужна: собираем кандидатов и вердикт модели руками и проверяем,
что решение принимает код, а не LLM.
"""
from __future__ import annotations

import pytest

from inn2domain.models import Candidate, Company, LLMVerdict, PageEvidence, Result
from inn2domain.pipeline import RESTRICTED_FLAG, SNIPPET_FLAG, Pipeline


def company(**kwargs) -> Company:
    base = dict(inn="7721581040", ogrn="5077746329876", name_short='ООО "ДЕЙТА КЬЮ"',
                brand="ДЕЙТА КЬЮ", city="Москва")
    base.update(kwargs)
    return Company(**base)


def candidate(domain: str, *, inn_found=False, city=False, name_sim=0.0, status=200,
              flags=None, developer=False) -> Candidate:
    return Candidate(
        domain=domain,
        flags=list(flags or []),
        evidence=[
            PageEvidence(
                url=f"https://{domain}/",
                http_status=status,
                inn_found=inn_found,
                developer_mention=developer,
                name_similarity=name_sim,
                city_found=city,
            )
        ],
    )


def decide(candidates: list[Candidate], verdict: LLMVerdict | None, comp: Company | None = None) -> Result:
    result = Result(inn="7721581040", company=comp or company(), candidates=candidates)
    confirmed = [c for c in candidates if c.inn_confirmed or c.ogrn_confirmed]
    Pipeline._decide(result, confirmed, verdict)
    return result


def test_requisites_win():
    result = decide([candidate("dadata.ru", inn_found=True)], None)
    assert result.domain == "dadata.ru"
    assert result.decided_by == "evidence"
    assert result.confidence >= 0.9


def test_requisites_beat_llm():
    verdict = LLMVerdict(domain="other.ru", confidence=0.9, reasoning="выбрал другой")
    result = decide([candidate("dadata.ru", inn_found=True), candidate("other.ru")], verdict)
    assert result.domain == "dadata.ru"
    assert result.decided_by == "evidence-over-llm"
    assert result.confidence < 0.9


def test_developer_requisites_are_not_evidence():
    """ИНН веб-студии в подвале не делает её сайт сайтом нашей компании."""
    weak = candidate("studio.ru", inn_found=True, developer=True)
    assert not weak.inn_confirmed
    result = decide([weak], LLMVerdict(domain="studio.ru", confidence=0.9))
    assert result.domain is None


def test_llm_needs_independent_support():
    """Совпало только название — этого мало (случай ООО "ПЛАСТ" и plast.ru)."""
    verdict = LLMVerdict(domain="plast.ru", confidence=0.8, reasoning="название совпало")
    result = decide([candidate("plast.ru", name_sim=1.0)], verdict)
    assert result.domain is None
    assert result.decided_by == "weak-support"


def test_llm_answer_with_snippet_support():
    verdict = LLMVerdict(domain="ozon.ru", confidence=0.8)
    result = decide([candidate("ozon.ru", flags=[SNIPPET_FLAG], status=403)], verdict)
    assert result.domain == "ozon.ru"
    assert result.decided_by == "llm"


def test_restricted_domain_never_wins_on_llm_opinion():
    verdict = LLMVerdict(domain="rusprofile.ru", confidence=0.95)
    result = decide([candidate("rusprofile.ru", flags=[RESTRICTED_FLAG], name_sim=1.0)], verdict)
    assert result.domain is None
    assert result.decided_by == "restricted-without-evidence"


def test_low_confidence_gives_null():
    verdict = LLMVerdict(domain="maybe.ru", confidence=0.4)
    result = decide([candidate("maybe.ru", city=True, name_sim=0.9)], verdict)
    assert result.domain is None


def test_dead_site_is_not_an_answer():
    verdict = LLMVerdict(domain="dead.ru", confidence=0.9)
    result = decide([candidate("dead.ru", status=502, flags=[SNIPPET_FLAG])], verdict)
    assert result.domain is None
    assert result.decided_by == "unreachable"


@pytest.mark.parametrize("brand,domain,city,expected", [
    ("ЯНДЕКС", "yandex.ru", True, "yandex.ru"),   # бренд и город совпали
    ("ЯНДЕКС", "yandex.ru", False, None),          # города на странице нет
])
def test_brand_plus_city_support(brand, domain, city, expected):
    verdict = LLMVerdict(domain=domain, confidence=0.8)
    result = decide(
        [candidate(domain, city=city, name_sim=0.9)],
        verdict,
        comp=company(brand=brand, name_short=f'ООО "{brand}"'),
    )
    assert result.domain == expected
