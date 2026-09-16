"""Оркестратор: ИНН -> домен.

Этапы:
  1. валидация ИНН по контрольной сумме;
  2. карточка организации из ЕГРЮЛ (DaData);
  3. несколько поисковых запросов: по ИНН, по названию, по названию с городом;
  4. сборка кандидатов: нормализация доменов, отсев агрегаторов и соцсетей;
  5. проверка кандидатов: качаем главную и страницы с реквизитами, ищем ИНН и ОГРН;
  6. решение LLM по собранным доказательствам, с проверкой ответа по списку кандидатов;
  7. политика: без твёрдых доказательств и при низкой уверенности отвечаем null.

Режимы (нужны для абляции в eval):
  search_only — базовый уровень: первый неагрегатор из выдачи;
  verify      — поиск с проверкой реквизитов, без LLM;
  full        — полный пайплайн.
"""
from __future__ import annotations

import time

from .cache import Cache
from .card import DaDataCardSource
from .config import Settings, get_settings
from .domains import domain_from_email, is_blocked, registrable_domain
from .extract import brand_matches_domain, find_requisite, name_similarity
from .fetch import PageFetcher, contact_links, html_to_text, page_title
from .inn import inn_kind, is_valid_inn, normalize_inn
from .llm import GigaChatClient, GigaChatError, SYSTEM_PROMPT, build_user_prompt, parse_json_object
from .models import Candidate, Company, LLMVerdict, PageEvidence, Result, SearchHit
from .search import build_search_provider

MAX_CANDIDATES_TO_VERIFY = 5
MAX_CONTACT_PAGES = 2
MAX_LLM_ROUNDS = 2
CONFIDENT_LLM_THRESHOLD = 0.6


class Pipeline:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        mode: str = "full",
        use_cache: bool = True,
        verbose: bool = False,
    ) -> None:
        self.settings = settings or get_settings()
        self.mode = mode
        self.verbose = verbose
        self.cache = Cache(self.settings.cache_path, self.settings.cache_ttl_days, enabled=use_cache)
        self.search = build_search_provider(self.settings, self.cache)
        self.cards = DaDataCardSource(self.settings, self.cache)
        self.fetcher = PageFetcher(self.settings, self.cache)
        self.llm = GigaChatClient(self.settings, self.cache)

    # --------------------------------------------------------------- шаги

    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"  · {message}")

    def build_queries(self, company: Company) -> list[str]:
        """Запрос по одному ИНН выводит агрегаторы, поэтому основной вес — на названии."""
        queries = [f'"{company.inn}"']
        brand = company.brand
        if brand:
            queries.append(f'"{brand}" официальный сайт')
            if company.city:
                queries.append(f'"{brand}" {company.city}')
        if company.name_short and company.name_short != brand:
            queries.append(f'{company.name_short} сайт')
        if not brand:
            queries.append(f"ИНН {company.inn} официальный сайт компании")
        return queries[:4]

    def collect_candidates(self, hits: list[SearchHit], company: Company) -> list[Candidate]:
        by_domain: dict[str, Candidate] = {}
        for hit in hits:
            domain = registrable_domain(hit.url)
            if not domain or is_blocked(domain):
                continue
            candidate = by_domain.setdefault(domain, Candidate(domain=domain))
            candidate.hits.append(hit)
            candidate.best_position = min(candidate.best_position, hit.position)
            if hit.query not in candidate.queries:
                candidate.queries.append(hit.query)
        # домен корпоративной почты из ЕГРЮЛ — отдельный кандидат
        for email in company.emails:
            domain = domain_from_email(email)
            if domain:
                candidate = by_domain.setdefault(domain, Candidate(domain=domain))
                candidate.from_email = True
        for candidate in by_domain.values():
            candidate.score = self._prior_score(candidate, company)
        return sorted(by_domain.values(), key=lambda c: -c.score)

    @staticmethod
    def _prior_score(candidate: Candidate, company: Company) -> float:
        """Предварительный вес — только по выдаче, до загрузки страниц."""
        score = 0.0
        score += max(0.0, 1.0 - (candidate.best_position - 1) * 0.12)
        score += 0.35 * (len(candidate.queries) - 1)
        score += 0.6 if candidate.from_email else 0.0
        score += 0.5 * brand_matches_domain(company.brand, candidate.domain)
        text = " ".join(f"{h.title} {h.snippet}" for h in candidate.hits)
        if company.inn in text.replace(" ", ""):
            score += 0.4
        score += 0.4 * name_similarity(company.brand or company.name_short, text)
        return round(score, 3)

    def verify_candidate(self, candidate: Candidate, company: Company) -> None:
        """Качаем сайт и ищем на нём реквизиты организации."""
        urls = [f"https://{candidate.domain}/"]
        seen: set[str] = set()
        while urls:
            url = urls.pop(0)
            if url in seen or len(candidate.evidence) >= 1 + MAX_CONTACT_PAGES:
                break
            seen.add(url)
            status, html, error = self.fetcher.get(url)
            if error and url.startswith("https://") and not candidate.evidence:
                # часть рунета до сих пор живёт без валидного TLS
                url = url.replace("https://", "http://", 1)
                if url not in seen:
                    seen.add(url)
                    status, html, error = self.fetcher.get(url)
            text = html_to_text(html) if html else ""
            inn_found, inn_context, inn_dev = find_requisite(text, company.inn)
            ogrn_found, ogrn_context, ogrn_dev = (False, None, False)
            if company.ogrn:
                ogrn_found, ogrn_context, ogrn_dev = find_requisite(text, company.ogrn)
            evidence = PageEvidence(
                url=url,
                http_status=status,
                title=page_title(html) if html else None,
                inn_found=inn_found,
                ogrn_found=ogrn_found,
                inn_context=inn_context or ogrn_context,
                developer_mention=(inn_dev and inn_found) or (ogrn_dev and ogrn_found),
                name_similarity=name_similarity(company.brand or company.name_short, text),
                excerpt=text[:900],
                error=error,
            )
            candidate.evidence.append(evidence)
            self._log(
                f"{url} -> {status or error}, ИНН={inn_found}, ОГРН={ogrn_found}, "
                f"название={evidence.name_similarity}"
            )
            if inn_found or ogrn_found:
                break
            if html and len(candidate.evidence) == 1:
                urls.extend(contact_links(html, url, limit=MAX_CONTACT_PAGES))
        candidate.score = round(candidate.score + self._evidence_bonus(candidate, company), 3)

    @staticmethod
    def _evidence_bonus(candidate: Candidate, company: Company) -> float:
        bonus = 0.0
        if candidate.inn_confirmed:
            bonus += 3.0
        if candidate.ogrn_confirmed:
            bonus += 1.5
        if any(e.developer_mention for e in candidate.evidence):
            bonus -= 1.0
            candidate.flags.append("реквизиты рядом с упоминанием разработчика сайта")
        if not candidate.reachable:
            bonus -= 1.5
            candidate.flags.append("сайт не открывается")
        bonus += 0.8 * candidate.best_name_similarity
        return bonus

    def ask_llm(self, company: Company, candidates: list[Candidate], attempt: int) -> LLMVerdict:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(company, candidates, attempt)},
        ]
        raw = self.llm.chat(messages)
        parsed = parse_json_object(raw)
        domain = parsed.get("domain")
        allowed = {c.domain for c in candidates}
        if domain and domain not in allowed:
            # модель выдумала домен — ответ не принимаем
            normalized = registrable_domain(str(domain))
            domain = normalized if normalized in allowed else None
        try:
            confidence = float(parsed.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        return LLMVerdict(
            domain=domain,
            confidence=max(0.0, min(1.0, confidence)),
            reasoning=str(parsed.get("reasoning") or "")[:500],
            extra_query=(parsed.get("extra_query") or None),
            raw=raw[:2000],
        )

    # --------------------------------------------------------------- запуск

    def run(self, raw_inn: str) -> Result:
        started = time.time()
        inn = normalize_inn(raw_inn)
        result = Result(inn=inn)
        if not is_valid_inn(inn):
            result.reason = "ИНН не проходит проверку контрольной суммы"
            result.decided_by = "validation"
            return result

        company = self.cards.get(inn)
        result.company = company
        self._log(f"карточка: {company.display_name} ({company.source}), город {company.city}")
        if company.source == "dadata-empty":
            result.reason = "Организация с таким ИНН не найдена в ЕГРЮЛ"
            result.decided_by = "validation"
            return result
        if inn_kind(inn) == "individual" and not company.brand:
            self._log("ИП без известного наименования: ищем только по ИНН")

        queries = self.build_queries(company)
        result.queries = list(queries)
        hits: list[SearchHit] = []
        for query in queries:
            try:
                found = self.search.search(query, limit=10)
            except Exception as exc:
                self._log(f"поиск не отработал ({query}): {exc}")
                continue
            self._log(f"запрос {query!r}: {len(found)} результатов")
            hits.extend(found)
        result.stats["search_queries"] = len(queries)

        candidates = self.collect_candidates(hits, company)
        if not candidates:
            result.reason = "Поиск не дал ни одного кандидата вне агрегаторов"
            result.decided_by = "no-candidates"
            result.stats["elapsed_sec"] = round(time.time() - started, 2)
            return result

        if self.mode == "search_only":
            best = candidates[0]
            result.domain = best.domain
            result.confidence = 0.5
            result.reason = "Базовый режим: первый неагрегатор из выдачи"
            result.decided_by = "search_only"
            result.candidates = candidates[:MAX_CANDIDATES_TO_VERIFY]
            result.stats["elapsed_sec"] = round(time.time() - started, 2)
            return result

        for candidate in candidates[:MAX_CANDIDATES_TO_VERIFY]:
            self.verify_candidate(candidate, company)
        candidates.sort(key=lambda c: -c.score)
        result.candidates = candidates[:MAX_CANDIDATES_TO_VERIFY]
        result.stats["pages_fetched"] = sum(len(c.evidence) for c in candidates)

        confirmed = [c for c in candidates if c.inn_confirmed or c.ogrn_confirmed]

        if self.mode == "verify":
            if len(confirmed) == 1:
                result.domain = confirmed[0].domain
                result.confidence = 0.95
                result.reason = "Реквизиты организации найдены на сайте"
                result.decided_by = "evidence"
            elif confirmed:
                result.reason = "Реквизиты найдены сразу на нескольких доменах, без LLM не разрешить"
                result.decided_by = "ambiguous"
            else:
                result.reason = "Реквизитов на сайтах кандидатов нет"
                result.decided_by = "no-evidence"
            result.stats["elapsed_sec"] = round(time.time() - started, 2)
            return result

        verdict = None
        if self.llm.available:
            for attempt in range(1, MAX_LLM_ROUNDS + 1):
                try:
                    verdict = self.ask_llm(company, result.candidates, attempt)
                except GigaChatError as exc:
                    self._log(f"LLM недоступна: {exc}")
                    break
                self._log(
                    f"LLM (попытка {attempt}): domain={verdict.domain}, "
                    f"confidence={verdict.confidence}, extra_query={verdict.extra_query}"
                )
                needs_more = verdict.domain is None or verdict.confidence < CONFIDENT_LLM_THRESHOLD
                if not (needs_more and verdict.extra_query and attempt < MAX_LLM_ROUNDS):
                    break
                # агентный шаг: модель просит дополнительный поиск
                try:
                    extra_hits = self.search.search(verdict.extra_query, limit=10)
                except Exception as exc:
                    self._log(f"дополнительный поиск не отработал: {exc}")
                    break
                result.queries.append(verdict.extra_query)
                result.stats["search_queries"] = len(result.queries)
                known = {c.domain for c in candidates}
                merged = self.collect_candidates(hits + extra_hits, company)
                for candidate in merged[:MAX_CANDIDATES_TO_VERIFY]:
                    if candidate.domain not in known:
                        self.verify_candidate(candidate, company)
                merged.sort(key=lambda c: -c.score)
                candidates = merged
                result.candidates = candidates[:MAX_CANDIDATES_TO_VERIFY]
                confirmed = [c for c in candidates if c.inn_confirmed or c.ogrn_confirmed]
        result.llm = verdict
        result.stats["llm_calls"] = self.llm.calls
        result.stats["llm_tokens"] = self.llm.tokens_used

        self._decide(result, confirmed, verdict)
        result.stats["elapsed_sec"] = round(time.time() - started, 2)
        return result

    @staticmethod
    def _decide(result: Result, confirmed: list[Candidate], verdict: LLMVerdict | None) -> None:
        """Политика ответа. Неверный домен дороже, чем null, поэтому пороги жёсткие."""
        top_confirmed = confirmed[0] if confirmed else None

        if top_confirmed and (verdict is None or verdict.domain in (None, top_confirmed.domain)):
            result.domain = top_confirmed.domain
            result.confidence = 0.97 if verdict and verdict.domain else 0.9
            result.reason = "Реквизиты организации опубликованы на сайте"
            result.decided_by = "evidence"
            return

        if top_confirmed and verdict and verdict.domain and verdict.domain != top_confirmed.domain:
            # расхождение фактов и модели: верим фактам, но уверенность снижаем
            result.domain = top_confirmed.domain
            result.confidence = 0.75
            result.reason = (
                "Реквизиты найдены на одном домене, LLM предложила другой. "
                f"Выбран домен с реквизитами. Аргумент LLM: {verdict.reasoning}"
            )
            result.decided_by = "evidence-over-llm"
            return

        if verdict and verdict.domain and verdict.confidence >= CONFIDENT_LLM_THRESHOLD:
            candidate = next((c for c in result.candidates if c.domain == verdict.domain), None)
            if candidate and not candidate.reachable:
                result.reason = "LLM выбрала домен, но сайт не открывается"
                result.decided_by = "unreachable"
                return
            result.domain = verdict.domain
            result.confidence = round(min(0.85, verdict.confidence), 2)
            result.reason = verdict.reasoning or "Решение LLM по косвенным признакам"
            result.decided_by = "llm"
            return

        result.reason = (
            verdict.reasoning
            if verdict and verdict.reasoning
            else "Твёрдых доказательств нет, уверенного ответа не получилось"
        )
        result.decided_by = "low-confidence"


def resolve(inn: str, **kwargs) -> Result:
    """Разовый вызов: удобно для тестов и API."""
    return Pipeline(**kwargs).run(inn)
