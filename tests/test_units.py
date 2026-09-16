"""Тесты на детерминированные части: валидация, нормализация, извлечение реквизитов."""
from __future__ import annotations

import pytest

from inn2domain.domains import domain_from_email, is_blocked, normalize_host, registrable_domain
from inn2domain.extract import brand_matches_domain, find_requisite, name_similarity
from inn2domain.inn import inn_kind, is_valid_inn, is_valid_ogrn
from inn2domain.card import strip_opf


@pytest.mark.parametrize("inn", ["7707083893", "7721581040", "500100732259"])
def test_valid_inn(inn):
    assert is_valid_inn(inn)


@pytest.mark.parametrize("inn", ["7707083894", "123", "", "77070838931", "abcdefghij"])
def test_invalid_inn(inn):
    assert not is_valid_inn(inn)


def test_inn_kind():
    assert inn_kind("7707083893") == "legal"
    assert inn_kind("500100732259") == "individual"


def test_ogrn():
    assert is_valid_ogrn("1027700132195")  # Сбербанк
    assert not is_valid_ogrn("1027700132196")


def test_normalize_host():
    assert normalize_host("https://WWW.Example.RU/path?a=1") == "example.ru"
    assert normalize_host("xn--80aqeigdi5k.xn--p1ai") == "компания.рф"
    assert normalize_host("not-a-host") is None


def test_registrable_domain():
    assert registrable_domain("https://shop.example.ru/a") == "example.ru"
    assert registrable_domain("https://my-shop.tilda.ws/") == "my-shop.tilda.ws"
    assert registrable_domain("https://firma.msk.ru/") == "firma.msk.ru"


def test_blocklist():
    assert is_blocked("rusprofile.ru")
    assert is_blocked("companies.rbc.ru")
    assert not is_blocked("dadata.ru")


def test_domain_from_email():
    assert domain_from_email("info@dadata.ru") == "dadata.ru"
    assert domain_from_email("info@mail.ru") is None
    assert domain_from_email("broken") is None


def test_find_requisite_plain():
    found, context, developer = find_requisite("Наш ИНН 7721581040, ОГРН ...", "7721581040")
    assert found and not developer
    assert "7721581040" in context


def test_find_requisite_with_separators():
    found, _, _ = find_requisite("ИНН 7721 581 040", "7721581040")
    assert found


def test_find_requisite_developer_trap():
    text = "Разработка сайта — ООО Веб-Студия, ИНН 7721581040"
    found, _, developer = find_requisite(text, "7721581040")
    assert found and developer


def test_find_requisite_absent():
    found, context, _ = find_requisite("ИНН 7707083893", "7721581040")
    assert not found and context is None


def test_strip_opf():
    assert strip_opf('ООО "Хоум Кредит"') == "Хоум Кредит"
    assert strip_opf("ПАО Сбербанк") == "Сбербанк"


def test_name_similarity():
    assert name_similarity("Ромашка Торг", "Компания Ромашка Торг, Москва") == 1.0
    assert name_similarity("Ромашка Торг", "Совсем другой текст") == 0.0


def test_brand_matches_domain():
    assert brand_matches_domain("Ромашка", "romashka.ru") == 1.0
    assert brand_matches_domain("Ромашка", "lenta.ru") < 0.5
