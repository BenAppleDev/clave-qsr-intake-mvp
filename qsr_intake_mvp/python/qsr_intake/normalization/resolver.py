from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Sequence

import numpy as np


@dataclass(frozen=True)
class TextFeatures:
    original_text: str
    cleaned_text: str
    readable_name: str
    slug: str
    tokens: tuple[str, ...]
    base_tokens: tuple[str, ...]
    size_tokens: tuple[str, ...]
    modifier_tokens: tuple[str, ...]


@dataclass(frozen=True)
class CatalogEntry:
    normalized_item_key: str
    normalized_item_name: str
    domains: tuple[str, ...]
    synonyms: tuple[str, ...]
    menu_categories: tuple[str, ...]
    price_band: dict[str, float] | None
    unit_of_measure: str | None
    variant_features: tuple[TextFeatures, ...]
    cleaned_menu_categories: tuple[str, ...]
    cleaned_unit_of_measure: str | None


@dataclass(frozen=True)
class CandidateScore:
    entry: CatalogEntry
    score: float
    vector_similarity: float
    token_similarity: float
    char_similarity: float
    category_bonus: float
    price_or_uom_bonus: float
    matched_text: str


@dataclass(frozen=True)
class ResolutionResult:
    normalized_item_key: str
    normalized_item_name: str
    confidence: float
    status: str
    method: str
    human_review_required: bool
    human_review_status: str
    debug_metadata: Dict[str, Any]


class EmbeddingProvider(ABC):
    provider_name = "embedding_provider"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    @abstractmethod
    def encode(self, texts: Sequence[str]) -> np.ndarray:
        raise NotImplementedError


class _DeterministicEmbeddingProvider(EmbeddingProvider):
    provider_name = "deterministic_fallback"

    def __init__(self, dim: int = 128) -> None:
        super().__init__(model_name="deterministic_fallback")
        self.dim = dim

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            grams = self._char_ngrams(text or "")
            if not grams:
                continue
            for gram in grams:
                digest = hashlib.sha256(gram.encode("utf-8")).digest()
                index = int.from_bytes(digest[:2], "big") % self.dim
                sign = 1.0 if digest[2] % 2 == 0 else -1.0
                vectors[row, index] += sign
        return _normalize_embeddings(vectors)

    @staticmethod
    def _char_ngrams(text: str) -> list[str]:
        padded = f"  {text.strip().lower()}  "
        if not padded.strip():
            return []
        return [padded[idx : idx + 3] for idx in range(max(len(padded) - 2, 0))]


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    provider_name = "sentence_transformer"
    _model_cache: dict[tuple[str, bool], Any] = {}

    def __init__(self, model_name: str, *, local_files_only: bool = True) -> None:
        super().__init__(model_name=model_name)
        self._cache: dict[str, np.ndarray] = {}
        self.local_files_only = local_files_only
        self.load_error: str | None = None
        self._fallback_provider: EmbeddingProvider | None = None
        self._model = self._load_model(model_name, local_files_only)
        if self._model is None:
            self.provider_name = "sentence_transformer_fallback"
            self._fallback_provider = _DeterministicEmbeddingProvider()

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        ordered = list(texts)
        uncached = [text for text in ordered if text not in self._cache]
        if uncached:
            embeddings = self._encode_uncached(uncached)
            for text, vector in zip(uncached, embeddings):
                self._cache[text] = vector
        return np.asarray([self._cache[text] for text in ordered], dtype=np.float32)

    def _encode_uncached(self, texts: Sequence[str]) -> np.ndarray:
        if self._model is None:
            assert self._fallback_provider is not None
            return self._fallback_provider.encode(texts)
        vectors = self._model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def _load_model(self, model_name: str, local_files_only: bool) -> Any:
        cache_key = (model_name, local_files_only)
        if cache_key in self._model_cache:
            return self._model_cache[cache_key]
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_name, device="cpu", local_files_only=local_files_only)
        except Exception as exc:  # pragma: no cover - depends on local model availability
            self.load_error = str(exc)
            return None
        self._model_cache[cache_key] = model
        return model


class CatalogResolver:
    def __init__(
        self,
        *,
        item_aliases: Dict[str, Dict[str, Any]],
        canonical_catalog: Sequence[Dict[str, Any]],
        resolver_config: Dict[str, Any],
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.resolver_version = resolver_config.get("version", "resolver_v1")
        self.catalog_version = resolver_config.get("catalog_version") or "catalog_v1"
        self.embedding_provider = embedding_provider
        self.item_aliases = {str(key).strip(): value for key, value in item_aliases.items()}

        thresholds = resolver_config.get("thresholds", {})
        self.auto_accept_threshold = float(thresholds.get("auto_accept_threshold", 0.92))
        self.review_threshold = float(thresholds.get("review_threshold", 0.78))
        self.close_candidate_margin = float(thresholds.get("close_candidate_margin", 0.03))

        weights = resolver_config.get("weights", {})
        self.weights = {
            "vector_similarity": float(weights.get("vector_similarity", 0.45)),
            "token_similarity": float(weights.get("token_similarity", 0.25)),
            "char_similarity": float(weights.get("char_similarity", 0.20)),
            "category_bonus": float(weights.get("category_bonus", 0.05)),
            "price_or_uom_bonus": float(weights.get("price_or_uom_bonus", 0.05)),
        }
        candidate_limits = resolver_config.get("candidate_limits", {})
        self.top_k = int(candidate_limits.get("top_k", 10))

        token_lexicon = resolver_config.get("token_lexicon", {})
        self.abbreviations = {str(key).lower(): str(value).lower() for key, value in token_lexicon.get("abbreviations", {}).items()}
        self.misspellings = {str(key).lower(): str(value).lower() for key, value in token_lexicon.get("misspellings", {}).items()}
        self.size_tokens = {str(token).lower() for token in token_lexicon.get("size_tokens", [])}
        self.modifier_tokens = {str(token).lower() for token in token_lexicon.get("modifier_tokens", [])}

        self.store_overrides = self._prepare_store_overrides(resolver_config.get("store_overrides", {}))
        self.cleaned_name_aliases = self._prepare_name_aliases(resolver_config.get("cleaned_name_aliases", {}))

        self.catalog_entries = [self._build_catalog_entry(entry) for entry in canonical_catalog]
        self.catalog_by_domain: dict[str, list[CatalogEntry]] = {}
        for entry in self.catalog_entries:
            for domain in entry.domains:
                self.catalog_by_domain.setdefault(domain, []).append(entry)

        self._text_embedding_cache: dict[str, np.ndarray] = {}
        self._prime_catalog_embeddings()

    def resolve(
        self,
        *,
        domain: str,
        source_store_id: str | None,
        source_item_code: str | None,
        source_name: str | None,
        menu_category: str | None = None,
        unit_price: float | None = None,
        unit_of_measure: str | None = None,
    ) -> ResolutionResult:
        source_features = self.extract_text_features(source_name or source_item_code or "unknown item")
        fallback_key = source_features.slug or self._slugify(source_item_code or "unknown item")
        fallback_name = source_features.readable_name or self._to_readable(source_item_code or "unknown item")
        source_code = (source_item_code or "").strip()

        if source_code in self.item_aliases:
            return self._build_exact_result(
                match=self.item_aliases[source_code],
                method="source_code_alias",
                domain=domain,
                source_features=source_features,
                fallback_key=fallback_key,
                matched_text=source_code,
                store_override_applied=False,
            )
        if source_code.upper() in self.item_aliases:
            return self._build_exact_result(
                match=self.item_aliases[source_code.upper()],
                method="source_code_alias",
                domain=domain,
                source_features=source_features,
                fallback_key=fallback_key,
                matched_text=source_code.upper(),
                store_override_applied=False,
            )

        override_match = self.store_overrides.get((source_store_id or "", domain, source_features.cleaned_text))
        if override_match is not None:
            return self._build_exact_result(
                match=override_match,
                method="store_override",
                domain=domain,
                source_features=source_features,
                fallback_key=fallback_key,
                matched_text=source_features.cleaned_text,
                store_override_applied=True,
            )

        alias_match = self.cleaned_name_aliases.get((domain, source_features.cleaned_text))
        if alias_match is not None:
            return self._build_exact_result(
                match=alias_match,
                method="name_alias",
                domain=domain,
                source_features=source_features,
                fallback_key=fallback_key,
                matched_text=source_features.cleaned_text,
                store_override_applied=False,
            )

        candidates = self._score_candidates(
            domain=domain,
            source_features=source_features,
            source_category=menu_category,
            unit_price=unit_price,
            unit_of_measure=unit_of_measure,
        )
        top_candidates = [self._candidate_to_debug(candidate) for candidate in candidates[: self.top_k]]

        if not candidates:
            return self._build_hybrid_result(
                status="unresolved",
                confidence=0.0,
                fallback_key=fallback_key,
                fallback_name=fallback_name,
                source_features=source_features,
                domain=domain,
                chosen_candidate=None,
                top_candidates=top_candidates,
            )

        best = candidates[0]
        runner_up = candidates[1] if len(candidates) > 1 else None
        close_margin = runner_up is not None and (best.score - runner_up.score) < self.close_candidate_margin
        if best.score >= self.auto_accept_threshold and not close_margin:
            return self._build_hybrid_result(
                status="matched",
                confidence=best.score,
                fallback_key=fallback_key,
                fallback_name=fallback_name,
                source_features=source_features,
                domain=domain,
                chosen_candidate=best,
                top_candidates=top_candidates,
            )
        if best.score >= self.review_threshold:
            return self._build_hybrid_result(
                status="review_required",
                confidence=best.score,
                fallback_key=fallback_key,
                fallback_name=fallback_name,
                source_features=source_features,
                domain=domain,
                chosen_candidate=best,
                top_candidates=top_candidates,
            )
        return self._build_hybrid_result(
            status="unresolved",
            confidence=best.score,
            fallback_key=fallback_key,
            fallback_name=fallback_name,
            source_features=source_features,
            domain=domain,
            chosen_candidate=best,
            top_candidates=top_candidates,
        )

    def extract_text_features(self, raw_text: str | None) -> TextFeatures:
        tokens: list[str] = []
        cleaned = raw_text or ""
        cleaned = cleaned.lower()
        cleaned = re.sub(r"[\*\?]+", "", cleaned)
        cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        for token in cleaned.split():
            expanded = self.abbreviations.get(token, token)
            corrected = self.misspellings.get(expanded, expanded)
            tokens.extend(part for part in corrected.split() if part)

        cleaned_text = " ".join(tokens)
        base_tokens = tuple(token for token in tokens if token not in self.size_tokens and token not in self.modifier_tokens)
        size_tokens = tuple(token for token in tokens if token in self.size_tokens)
        modifier_tokens = tuple(token for token in tokens if token in self.modifier_tokens)
        readable_name = self._to_readable(cleaned_text)
        return TextFeatures(
            original_text=raw_text or "",
            cleaned_text=cleaned_text,
            readable_name=readable_name,
            slug=self._slugify(cleaned_text),
            tokens=tuple(tokens),
            base_tokens=base_tokens,
            size_tokens=size_tokens,
            modifier_tokens=modifier_tokens,
        )

    def _prepare_store_overrides(self, config: Dict[str, Any]) -> dict[tuple[str, str, str], Dict[str, Any]]:
        prepared: dict[tuple[str, str, str], Dict[str, Any]] = {}
        for store_id, domains in config.items():
            for domain, names in (domains or {}).items():
                for raw_name, match in (names or {}).items():
                    cleaned = self.extract_text_features(raw_name).cleaned_text
                    prepared[(str(store_id), str(domain), cleaned)] = dict(match)
        return prepared

    def _prepare_name_aliases(self, config: Dict[str, Any]) -> dict[tuple[str, str], Dict[str, Any]]:
        prepared: dict[tuple[str, str], Dict[str, Any]] = {}
        for domain, names in config.items():
            for raw_name, match in (names or {}).items():
                cleaned = self.extract_text_features(raw_name).cleaned_text
                prepared[(str(domain), cleaned)] = dict(match)
        return prepared

    def _build_catalog_entry(self, config: Dict[str, Any]) -> CatalogEntry:
        name = str(config["normalized_item_name"])
        synonyms = tuple(str(value) for value in config.get("synonyms", []))
        domains = tuple(str(domain) for domain in config.get("domains", []))
        menu_categories = tuple(str(value) for value in config.get("menu_categories", []))
        variant_features = tuple(
            self.extract_text_features(text)
            for text in dict.fromkeys([name, *synonyms])
            if self.extract_text_features(text).cleaned_text
        )
        return CatalogEntry(
            normalized_item_key=str(config["normalized_item_key"]),
            normalized_item_name=name,
            domains=domains,
            synonyms=synonyms,
            menu_categories=menu_categories,
            price_band=config.get("price_band"),
            unit_of_measure=config.get("unit_of_measure"),
            variant_features=variant_features,
            cleaned_menu_categories=tuple(
                feature.cleaned_text
                for feature in (self.extract_text_features(category) for category in menu_categories)
                if feature.cleaned_text
            ),
            cleaned_unit_of_measure=self.extract_text_features(config.get("unit_of_measure") or "").cleaned_text or None,
        )

    def _prime_catalog_embeddings(self) -> None:
        texts = sorted(
            {
                feature.cleaned_text
                for entry in self.catalog_entries
                for feature in entry.variant_features
                if feature.cleaned_text
            }
        )
        if not texts:
            return
        embeddings = self.embedding_provider.encode(texts)
        for text, vector in zip(texts, embeddings):
            self._text_embedding_cache[text] = vector

    def _score_candidates(
        self,
        *,
        domain: str,
        source_features: TextFeatures,
        source_category: str | None,
        unit_price: float | None,
        unit_of_measure: str | None,
    ) -> List[CandidateScore]:
        candidates = list(self.catalog_by_domain.get(domain, []))
        if not candidates:
            return []
        source_category_cleaned = self.extract_text_features(source_category or "").cleaned_text
        if source_category_cleaned:
            category_filtered = [entry for entry in candidates if source_category_cleaned in entry.cleaned_menu_categories]
            if category_filtered:
                candidates = category_filtered

        source_vector = self._embedding_provider_vector(source_features.cleaned_text)
        scored: list[CandidateScore] = []
        for entry in candidates:
            vector_similarity = 0.0
            token_similarity = 0.0
            char_similarity = 0.0
            matched_text = entry.normalized_item_name
            for variant in entry.variant_features:
                variant_vector = self._embedding_provider_vector(variant.cleaned_text)
                current_vector = float(np.dot(source_vector, variant_vector))
                current_token = self._token_similarity(source_features, variant)
                current_char = SequenceMatcher(a=source_features.cleaned_text, b=variant.cleaned_text).ratio()
                if (current_vector, current_token, current_char) > (vector_similarity, token_similarity, char_similarity):
                    vector_similarity = current_vector
                    token_similarity = current_token
                    char_similarity = current_char
                    matched_text = variant.cleaned_text
            category_bonus = 1.0 if source_category_cleaned and source_category_cleaned in entry.cleaned_menu_categories else 0.0
            price_or_uom_bonus = self._price_or_uom_bonus(
                domain=domain,
                entry=entry,
                unit_price=unit_price,
                unit_of_measure=unit_of_measure,
            )
            total_score = (
                (self.weights["vector_similarity"] * vector_similarity)
                + (self.weights["token_similarity"] * token_similarity)
                + (self.weights["char_similarity"] * char_similarity)
                + (self.weights["category_bonus"] * category_bonus)
                + (self.weights["price_or_uom_bonus"] * price_or_uom_bonus)
            )
            scored.append(
                CandidateScore(
                    entry=entry,
                    score=round(max(0.0, min(total_score, 1.0)), 4),
                    vector_similarity=round(max(0.0, min(vector_similarity, 1.0)), 4),
                    token_similarity=round(max(0.0, min(token_similarity, 1.0)), 4),
                    char_similarity=round(max(0.0, min(char_similarity, 1.0)), 4),
                    category_bonus=round(category_bonus, 4),
                    price_or_uom_bonus=round(price_or_uom_bonus, 4),
                    matched_text=matched_text,
                )
            )
        return sorted(scored, key=lambda candidate: (candidate.score, candidate.vector_similarity, candidate.token_similarity), reverse=True)[: self.top_k]

    def _build_exact_result(
        self,
        *,
        match: Dict[str, Any],
        method: str,
        domain: str,
        source_features: TextFeatures,
        fallback_key: str,
        matched_text: str,
        store_override_applied: bool,
    ) -> ResolutionResult:
        confidence = float(match.get("confidence", 1.0))
        key = str(match["normalized_item_key"])
        debug_metadata = self._base_debug_metadata(
            source_features=source_features,
            domain=domain,
            chosen_key=key,
            top_candidates=[],
            method=method,
            status="matched",
            store_override_applied=store_override_applied,
            vector_similarity=1.0,
            token_similarity=1.0,
            char_similarity=1.0,
            category_bonus=0.0,
            price_or_uom_bonus=0.0,
        )
        debug_metadata["matched_text"] = matched_text
        debug_metadata["fallback_key"] = fallback_key
        return ResolutionResult(
            normalized_item_key=key,
            normalized_item_name=str(match["normalized_item_name"]),
            confidence=round(confidence, 4),
            status="matched",
            method=method,
            human_review_required=False,
            human_review_status="not_required",
            debug_metadata=debug_metadata,
        )

    def _build_hybrid_result(
        self,
        *,
        status: str,
        confidence: float,
        fallback_key: str,
        fallback_name: str,
        source_features: TextFeatures,
        domain: str,
        chosen_candidate: CandidateScore | None,
        top_candidates: List[Dict[str, Any]],
    ) -> ResolutionResult:
        human_review_required = status != "matched"
        human_review_status = "pending" if human_review_required else "not_required"
        chosen_key = chosen_candidate.entry.normalized_item_key if status == "matched" and chosen_candidate else fallback_key
        chosen_name = chosen_candidate.entry.normalized_item_name if status == "matched" and chosen_candidate else fallback_name
        debug_metadata = self._base_debug_metadata(
            source_features=source_features,
            domain=domain,
            chosen_key=chosen_key,
            top_candidates=top_candidates,
            method="hybrid_vector",
            status=status,
            store_override_applied=False,
            vector_similarity=chosen_candidate.vector_similarity if chosen_candidate else 0.0,
            token_similarity=chosen_candidate.token_similarity if chosen_candidate else 0.0,
            char_similarity=chosen_candidate.char_similarity if chosen_candidate else 0.0,
            category_bonus=chosen_candidate.category_bonus if chosen_candidate else 0.0,
            price_or_uom_bonus=chosen_candidate.price_or_uom_bonus if chosen_candidate else 0.0,
        )
        if chosen_candidate is not None:
            debug_metadata["matched_text"] = chosen_candidate.matched_text
            debug_metadata["best_candidate_key"] = chosen_candidate.entry.normalized_item_key
            debug_metadata["best_candidate_name"] = chosen_candidate.entry.normalized_item_name
        debug_metadata["fallback_key"] = fallback_key
        debug_metadata["fallback_name"] = fallback_name
        return ResolutionResult(
            normalized_item_key=chosen_key,
            normalized_item_name=chosen_name,
            confidence=round(confidence, 4),
            status=status,
            method="hybrid_vector",
            human_review_required=human_review_required,
            human_review_status=human_review_status,
            debug_metadata=debug_metadata,
        )

    def _base_debug_metadata(
        self,
        *,
        source_features: TextFeatures,
        domain: str,
        chosen_key: str,
        top_candidates: List[Dict[str, Any]],
        method: str,
        status: str,
        store_override_applied: bool,
        vector_similarity: float,
        token_similarity: float,
        char_similarity: float,
        category_bonus: float,
        price_or_uom_bonus: float,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "method": method,
            "source_cleaned_name": source_features.cleaned_text,
            "domain": domain,
            "chosen_key": chosen_key,
            "top_candidates": top_candidates,
            "token_similarity": round(token_similarity, 4),
            "vector_similarity": round(vector_similarity, 4),
            "char_similarity": round(char_similarity, 4),
            "category_bonus": round(category_bonus, 4),
            "price_or_uom_bonus": round(price_or_uom_bonus, 4),
            "store_override_applied": store_override_applied,
            "catalog_version": self.catalog_version,
            "resolver_version": self.resolver_version,
            "embedding_provider": self.embedding_provider.provider_name,
            "embedding_model_name": self.embedding_provider.model_name,
        }

    def _candidate_to_debug(self, candidate: CandidateScore) -> Dict[str, Any]:
        return {
            "normalized_item_key": candidate.entry.normalized_item_key,
            "normalized_item_name": candidate.entry.normalized_item_name,
            "score": candidate.score,
            "vector_similarity": candidate.vector_similarity,
            "token_similarity": candidate.token_similarity,
            "char_similarity": candidate.char_similarity,
            "category_bonus": candidate.category_bonus,
            "price_or_uom_bonus": candidate.price_or_uom_bonus,
            "matched_text": candidate.matched_text,
        }

    def _embedding_provider_vector(self, text: str) -> np.ndarray:
        if text not in self._text_embedding_cache:
            self._text_embedding_cache[text] = self.embedding_provider.encode([text])[0]
        return self._text_embedding_cache[text]

    def _token_similarity(self, source: TextFeatures, candidate: TextFeatures) -> float:
        all_similarity = _set_similarity(source.tokens, candidate.tokens)
        base_similarity = _set_similarity(source.base_tokens, candidate.base_tokens)
        return round((0.3 * all_similarity) + (0.7 * base_similarity), 4)

    def _price_or_uom_bonus(
        self,
        *,
        domain: str,
        entry: CatalogEntry,
        unit_price: float | None,
        unit_of_measure: str | None,
    ) -> float:
        if domain == "line_item" and unit_price is not None and entry.price_band:
            low = float(entry.price_band.get("min", unit_price))
            high = float(entry.price_band.get("max", unit_price))
            return 1.0 if low <= float(unit_price) <= high else 0.0
        if domain == "inventory" and unit_of_measure and entry.cleaned_unit_of_measure:
            cleaned_uom = self.extract_text_features(unit_of_measure).cleaned_text
            return 1.0 if cleaned_uom == entry.cleaned_unit_of_measure else 0.0
        return 0.0

    @staticmethod
    def _slugify(text: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
        return slug or "unknown_item"

    @staticmethod
    def _to_readable(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            return "Unknown Item"
        return " ".join(part.capitalize() for part in cleaned.split())


def _normalize_embeddings(vectors: np.ndarray) -> np.ndarray:
    if vectors.size == 0:
        return vectors.astype(np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return (vectors / norms).astype(np.float32)


def _set_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    if not left_set or not right_set:
        return 0.0
    overlap = len(left_set & right_set)
    return (2 * overlap) / (len(left_set) + len(right_set))
