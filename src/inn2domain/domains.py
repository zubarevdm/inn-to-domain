"""Нормализация доменов и блок-лист источников, которые сайтом организации не являются."""
from __future__ import annotations

from urllib.parse import urlsplit

# Домены второго уровня, на которых регистрируют сайты третьего уровня.
# Для них значимым именем является хост целиком (a.msk.ru != b.msk.ru).
MULTI_LEVEL_SUFFIXES = {
    "com.ru", "net.ru", "org.ru", "pp.ru", "msk.ru", "spb.ru", "nov.ru", "sochi.ru",
    "co.uk", "org.uk", "com.tr", "com.ua", "co.il", "com.cn", "co.jp",
}

# Конструкторы сайтов и бесплатные хостинги: сайт живёт на поддомене,
# поэтому схлопывать его до домена второго уровня нельзя.
SITE_PLATFORMS = {
    "tilda.ws", "tilda.cc", "nethouse.ru", "ucoz.ru", "ucoz.net", "narod.ru", "wixsite.com",
    "business.site", "bitrix24.ru", "bitrix24.site", "shop2.ru", "insales.ru", "prom.ua",
    "github.io", "wordpress.com", "blogspot.com", "jimdosite.com", "creatium.site",
    "taplink.ws", "readymag.com", "webflow.io",
}

# Агрегаторы реквизитов, госреестры, соцсети, маркетплейсы, СМИ, карты, работа.
#
# Полностью выкидывать их нельзя: каждый такой портал сам является сайтом
# какой-то организации (ozon.ru — сайт ООО "Интернет Решения", yandex.ru —
# сайт ООО "Яндекс"). Поэтому правило мягче: такой домен проходит дальше
# только если реквизиты организации найдены на его главной или странице
# контактов. Чужие ИНН эти площадки публикуют на глубоких страницах
# (карточка продавца, карточка контрагента, вакансия), куда пайплайн не ходит,
# так что ложных срабатываний это не добавляет.
RESTRICTED_DOMAINS = {
    # агрегаторы отчётности и реквизитов
    "rusprofile.ru", "list-org.com", "checko.ru", "zachestnyibiznes.ru", "sbis.ru",
    "audit-it.ru", "kartoteka.ru", "sparkinterfax.ru", "spark-interfax.ru", "seldon.ru",
    "synapsenet.ru", "testfirm.ru", "vypiska-nalog.com", "e-disclosure.ru",
    "delovoy-profil.ru", "ogrn.online", "vestnik-gosreg.ru", "damia.ru",
    "kontur.ru", "kontur-f.ru", "sbis24.ru", "rbc.ru",
    # найдены при разметке выборки: тоже публикуют реквизиты чужих организаций
    "star-pro.ru", "prima-inform.ru", "datanewton.ru", "b2b.house", "vbankcenter.ru",
    "1prime.ru", "klerk.ru", "b2b-center.ru", "vbr.ru", "sravni.ru", "pikabu.ru",
    "rusbase.com", "zaimo.ru", "sbercrm.ru", "companies.wiki", "kompaniya.org",
    "sbis.com", "ru-bezh.ru", "vipiska-nalog.com", "egrul.ru", "ogrn.ru",
    "companium.ru", "xfirm.ru", "b2b-69.ru", "companies.wiki", "kompaniya.org",
    # финансовые и биржевые справочники, рейтинги, закупочные площадки
    "banki.ru", "bankiros.ru", "brobank.ru", "1000bankov.ru", "moex.com",
    "cbonds.ru", "rusbonds.ru", "raexpert.ru", "raex-rr.com", "acra-ratings.ru",
    "otc.ru", "tender.pro", "alta.ru", "rts-tender.ru", "roseltorg.ru",
    "lichniekabineti.ru", "mojkabinet.ru", "rsr-online.ru", "onrender.com",
    # сайты банков и сервисов со встроенной проверкой контрагентов
    "saby.ru", "tochka.com", "tbank.ru", "alfabank.ru", "sberbank.ru", "vtb.ru",
    "modulbank.ru", "psbank.ru", "open.ru", "raiffeisen.ru", "gazprombank.ru",
    # госресурсы
    "nalog.gov.ru", "nalog.ru", "egrul.nalog.ru", "zakupki.gov.ru", "bus.gov.ru",
    "fedresurs.ru", "gosuslugi.ru", "kad.arbitr.ru", "sudact.ru", "pb.nalog.ru",
    "rkn.gov.ru", "fssp.gov.ru", "cbr.ru", "rosstat.gov.ru", "bo.nalog.ru",
    # соцсети и мессенджеры
    "vk.com", "vk.ru", "ok.ru", "t.me", "telegram.me", "facebook.com", "instagram.com",
    "youtube.com", "rutube.ru", "dzen.ru", "livejournal.com", "x.com",
    "twitter.com", "linkedin.com", "pinterest.com", "tiktok.com", "tenchat.ru",
    # маркетплейсы, карты, отзывы, работа
    "wildberries.ru", "ozon.ru", "avito.ru", "yandex.ru", "ya.ru",
    "2gis.ru", "2gis.com", "zoon.ru", "yell.ru", "flamp.ru", "orgpage.ru", "spr.ru",
    "hh.ru", "superjob.ru", "rabota.ru", "zarplata.ru", "trud.com", "gorodrabot.ru",
    "prodoctorov.ru", "otzovik.com", "irecommend.ru", "youla.ru",
    "pulscen.ru", "tiu.ru", "satom.ru", "blizko.ru", "regmarkets.ru",
    # справочники и СМИ
    "wikipedia.org", "kommersant.ru", "interfax.ru",
    "tass.ru", "ria.ru", "vedomosti.ru", "forbes.ru", "cnews.ru", "habr.com",
    # техническое
    "web.archive.org", "archive.org", "google.com", "bing.com", "mail.ru", "gmail.com",
    "yadi.sk",
}

# Почтовые домены: адрес на них ничего не говорит о сайте организации.
FREE_MAIL_DOMAINS = {
    "mail.ru", "inbox.ru", "bk.ru", "list.ru", "internet.ru", "yandex.ru", "ya.ru",
    "gmail.com", "rambler.ru", "icloud.com", "outlook.com", "hotmail.com", "yahoo.com",
}


def normalize_host(url_or_host: str | None) -> str | None:
    """URL или хост -> хост в нижнем регистре, без www, punycode раскрыт в юникод."""
    if not url_or_host:
        return None
    raw = url_or_host.strip()
    if "//" not in raw:
        raw = "//" + raw
    host = (urlsplit(raw).hostname or "").strip(".").lower()
    if not host or "." not in host:
        return None
    if host.startswith("www."):
        host = host[4:]
    if "xn--" in host:
        try:
            host = host.encode("ascii").decode("idna")
        except Exception:
            pass
    return host or None


def registrable_domain(host: str | None) -> str | None:
    """Схлопываем поддомены до значимого имени.

    shop.example.ru -> example.ru, но my-shop.tilda.ws остаётся целиком:
    на конструкторе сайтов поддомен и есть сайт компании.
    """
    host = normalize_host(host)
    if not host:
        return None
    parts = host.split(".")
    for platform in SITE_PLATFORMS:
        if host == platform:
            return host
        if host.endswith("." + platform):
            keep = len(platform.split(".")) + 1
            return ".".join(parts[-keep:])
    for suffix in MULTI_LEVEL_SUFFIXES:
        if host.endswith("." + suffix):
            return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) > 2 else host


def is_restricted(domain: str | None) -> bool:
    """Домен допустим только при подтверждённых реквизитах на главной или в контактах."""
    if not domain:
        return True
    if domain in RESTRICTED_DOMAINS:
        return True
    # поддомены тех же ресурсов (companies.rbc.ru и т.п.)
    return any(domain.endswith("." + restricted) for restricted in RESTRICTED_DOMAINS)


def domain_from_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    domain = registrable_domain(email.rsplit("@", 1)[1])
    if not domain or domain in FREE_MAIL_DOMAINS or is_restricted(domain):
        return None
    return domain
