from __future__ import annotations

import numpy as np

from qsr_intake.normalization.resolver import CatalogResolver, EmbeddingProvider


class FakeEmbeddingProvider(EmbeddingProvider):
    provider_name = "fake"

    def __init__(self, mapping: dict[str, list[float]], dim: int = 3) -> None:
        super().__init__(model_name="fake")
        self.mapping = {key: np.asarray(value, dtype=np.float32) for key, value in mapping.items()}
        self.dim = dim

    def encode(self, texts):
        rows = []
        for text in texts:
            rows.append(self.mapping.get(text, np.zeros(self.dim, dtype=np.float32)))
        matrix = np.asarray(rows, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return matrix / norms


def test_source_code_alias_precedence_over_other_paths():
    resolver = _build_resolver(
        item_aliases={
            "SKU-1": {
                "normalized_item_key": "burger_classic",
                "normalized_item_name": "Classic Burger",
                "confidence": 1.0,
            }
        }
    )
    result = resolver.resolve(
        domain="line_item",
        source_store_id="toast-chi-001",
        source_item_code="SKU-1",
        source_name="House Fries",
        menu_category="Sides",
        unit_price=3.50,
    )
    assert result.method == "source_code_alias"
    assert result.status == "matched"
    assert result.normalized_item_key == "burger_classic"


def test_store_override_precedence_over_name_alias_and_vector():
    resolver = _build_resolver(
        embedding_map={
            "house fries": [1.0, 0.0, 0.0],
            "large fries": [1.0, 0.0, 0.0],
            "medium fries": [0.9, 0.1, 0.0],
            "fries": [1.0, 0.0, 0.0],
        }
    )
    result = resolver.resolve(
        domain="line_item",
        source_store_id="toast-la-001",
        source_item_code="UNKNOWN",
        source_name="House Fries",
        menu_category="Sides",
        unit_price=4.50,
    )
    assert result.method == "store_override"
    assert result.normalized_item_key == "fries_large"


def test_tokenizer_cleanup_handles_noise_sizes_and_misspellings():
    resolver = _build_resolver()
    features = resolver.extract_text_features("Lrg Clsc Burg*r///Combo??")
    assert features.cleaned_text == "large classic burger combo"
    assert features.base_tokens == ("classic", "burger")
    assert features.size_tokens == ("large",)
    assert features.modifier_tokens == ("combo",)
    assert features.slug == "large_classic_burger_combo"


def test_hybrid_candidate_scores_auto_accept():
    resolver = _build_resolver(
        embedding_map={
            "large classic burger": [1.0, 0.0, 0.0],
            "classic burger": [0.99, 0.01, 0.0],
            "burger classic": [0.99, 0.01, 0.0],
            "large fries": [0.0, 1.0, 0.0],
            "medium fries": [0.0, 1.0, 0.0],
            "fries": [0.0, 1.0, 0.0],
        }
    )
    result = resolver.resolve(
        domain="line_item",
        source_store_id="toast-chi-001",
        source_item_code="UNKNOWN",
        source_name="Lrg Clsc Burg*r",
        menu_category="Entrees",
        unit_price=9.40,
    )
    assert result.status == "matched"
    assert result.method == "hybrid_vector"
    assert result.normalized_item_key == "burger_classic"
    assert result.confidence >= 0.92


def test_close_margin_triggers_review_required():
    resolver = _build_resolver(
        embedding_map={
            "fries": [0.0, 1.0, 0.0],
            "large fries": [0.0, 1.0, 0.0],
            "medium fries": [0.0, 1.0, 0.0],
        }
    )
    result = resolver.resolve(
        domain="line_item",
        source_store_id="toast-chi-001",
        source_item_code="UNKNOWN",
        source_name="Fries??",
        menu_category="Sides",
        unit_price=3.95,
    )
    assert result.status == "review_required"
    assert result.human_review_required is True
    assert result.normalized_item_key == "fries"
    assert result.human_review_status == "pending"


def test_unresolved_below_review_threshold():
    resolver = _build_resolver(
        embedding_map={
            "nebula slush": [0.1, 0.1, 0.1],
            "classic burger": [1.0, 0.0, 0.0],
            "large classic burger": [1.0, 0.0, 0.0],
            "medium fries": [0.0, 1.0, 0.0],
            "large fries": [0.0, 1.0, 0.0],
            "fries": [0.0, 1.0, 0.0],
            "cola": [0.0, 0.0, 1.0],
        }
    )
    result = resolver.resolve(
        domain="line_item",
        source_store_id="toast-chi-001",
        source_item_code="UNKNOWN",
        source_name="Nebula Slush",
        menu_category="Beverages",
        unit_price=5.75,
    )
    assert result.status == "unresolved"
    assert result.human_review_required is True
    assert result.normalized_item_key == "nebula_slush"


def _build_resolver(
    *,
    item_aliases: dict | None = None,
    embedding_map: dict[str, list[float]] | None = None,
) -> CatalogResolver:
    config = {
        "version": "resolver_v1",
        "catalog_version": "catalog_v1",
        "thresholds": {
            "auto_accept_threshold": 0.92,
            "review_threshold": 0.78,
            "close_candidate_margin": 0.03,
        },
        "candidate_limits": {"top_k": 10},
        "weights": {
            "vector_similarity": 0.45,
            "token_similarity": 0.25,
            "char_similarity": 0.20,
            "category_bonus": 0.05,
            "price_or_uom_bonus": 0.05,
        },
        "token_lexicon": {
            "abbreviations": {
                "md": "medium",
                "med": "medium",
                "lg": "large",
                "lrg": "large",
                "clsc": "classic",
                "burgr": "burger",
            },
            "misspellings": {
                "frise": "fries",
                "pattie": "patty",
            },
            "size_tokens": ["small", "medium", "large"],
            "modifier_tokens": ["combo", "deluxe", "basket", "regular", "house"],
        },
        "store_overrides": {
            "toast-la-001": {
                "line_item": {
                    "house fries": {
                        "normalized_item_key": "fries_large",
                        "normalized_item_name": "Large Fries",
                        "confidence": 0.995,
                    }
                }
            }
        },
        "cleaned_name_aliases": {
            "line_item": {
                "house fries": {
                    "normalized_item_key": "fries_medium",
                    "normalized_item_name": "Medium Fries",
                    "confidence": 0.98,
                },
                "cola": {
                    "normalized_item_key": "soda_cola",
                    "normalized_item_name": "Cola",
                    "confidence": 0.98,
                },
            }
        },
    }
    catalog = [
        {
            "normalized_item_key": "burger_classic",
            "normalized_item_name": "Classic Burger",
            "domains": ["line_item"],
            "synonyms": ["Large Classic Burger", "Burger Classic"],
            "menu_categories": ["Entrees"],
            "price_band": {"min": 8.50, "max": 10.00},
        },
        {
            "normalized_item_key": "fries_medium",
            "normalized_item_name": "Medium Fries",
            "domains": ["line_item"],
            "synonyms": ["Fries", "Fries Medium"],
            "menu_categories": ["Sides"],
            "price_band": {"min": 3.00, "max": 3.80},
        },
        {
            "normalized_item_key": "fries_large",
            "normalized_item_name": "Large Fries",
            "domains": ["line_item"],
            "synonyms": ["Fries", "Fries Large"],
            "menu_categories": ["Sides"],
            "price_band": {"min": 4.10, "max": 4.80},
        },
        {
            "normalized_item_key": "soda_cola",
            "normalized_item_name": "Cola",
            "domains": ["line_item"],
            "synonyms": ["Soda Cola"],
            "menu_categories": ["Beverages"],
            "price_band": {"min": 2.00, "max": 3.00},
        },
    ]
    provider = FakeEmbeddingProvider(
        embedding_map
        or {
            "classic burger": [1.0, 0.0, 0.0],
            "large classic burger": [1.0, 0.0, 0.0],
            "burger classic": [1.0, 0.0, 0.0],
            "fries": [0.0, 1.0, 0.0],
            "medium fries": [0.0, 1.0, 0.0],
            "fries medium": [0.0, 1.0, 0.0],
            "large fries": [0.0, 1.0, 0.0],
            "fries large": [0.0, 1.0, 0.0],
            "cola": [0.0, 0.0, 1.0],
            "soda cola": [0.0, 0.0, 1.0],
            "house fries": [0.0, 1.0, 0.0],
        }
    )
    return CatalogResolver(
        item_aliases=item_aliases or {},
        canonical_catalog=catalog,
        resolver_config=config,
        embedding_provider=provider,
    )
