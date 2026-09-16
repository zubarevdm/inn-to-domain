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


def test_llm_arbitrates_contested_requisites():
    """ИНН публикуют и партнёры, и филиалы, и агрегаторы.

    Когда модель называет другой домен, решает она, но её выбор обязан иметь
    независимую опору. Здесь она есть: домен пришёл по запросу с ИНН.
    """
    verdict = LLMVerdict(domain="other.ru", confidence=0.9, reasoning="выбрал другой")
    other = candidate("other.ru")
    other.from_inn_query = True
    other.inn_query_position = 2
    result = decide([candidate("partner.ru", inn_found=True), other], verdict)
    assert result.domain == "other.ru"
    assert result.decided_by == "llm-over-evidence"
    assert result.confidence <= 0.8


def test_requisites_win_when_llm_agrees_or_silent():
    result = decide([candidate("dadata.ru", inn_found=True), candidate("other.ru")], None)
    assert result.domain == "dadata.ru"
    assert result.decided_by == "evidence"


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


def test_inn_query_origin_is_support():
    """Домен пришёл по запросу с ИНН: выдача описывала именно эту организацию."""
    verdict = LLMVerdict(domain="tbank.ru", confidence=0.8)
    hit = candidate("tbank.ru", name_sim=0.5)
    hit.from_inn_query = True
    hit.inn_query_position = 1
    result = decide([hit], verdict)
    assert result.domain == "tbank.ru"


def test_low_rank_in_inn_query_is_not_support():
    """По запросу с ИНН выдача забита агрегаторами, хвост её ничего не значит."""
    verdict = LLMVerdict(domain="random.ru", confidence=0.8)
    hit = candidate("random.ru", name_sim=0.5)
    hit.from_inn_query = True
    hit.inn_query_position = 9
    result = decide([hit], verdict)
    assert result.domain is None


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
    """502 это сломанный сервер, ответом такой домен быть не может."""
    verdict = LLMVerdict(domain="dead.ru", confidence=0.9)
    result = decide([candidate("dead.ru", status=502, flags=[SNIPPET_FLAG])], verdict)
    assert result.domain is None
    assert result.decided_by == "unreachable"


@pytest.mark.parametrize("brand,domain,city,expected", [
    ("ЯНДЕКС", "yandex.ru", True, "yandex.ru"),          # бренд равен домену и город совпал
    ("ТРАНСНЕФТЬ", "transneft.ru", True, "transneft.ru"),
    ("ПЛАСТ", "plast.ru", False, None),                  # чужой сайт с тем же названием
    ("РЕСУРС", "gapresurs.ru", True, None),              # "ресурс" внутри чужого имени
    ("СОФТ", "syssoft.ru", True, None),
])
def test_brand_to_domain_support(brand, domain, city, expected):
    """Совпадение бренда с доменом работает только вместе со вторым признаком."""
    verdict = LLMVerdict(domain=domain, confidence=0.8)
    result = decide(
        [candidate(domain, name_sim=0.9, city=city)],
        verdict,
        comp=company(brand=brand, name_short=f'ООО "{brand}"'),
    )
    assert result.domain == expected
