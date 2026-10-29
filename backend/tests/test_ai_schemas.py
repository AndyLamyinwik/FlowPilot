"""Offline contracts for provider-neutral text input and safe response metadata."""

from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from app.ai.schemas import (
    AIMessage, AIProviderCapabilities, AIProviderMetadata, AIRequest, AIResponse,
    AIUsage, MAX_METADATA_DEPTH,
)


def request(**updates):
    return AIRequest.model_validate({
        "model": "example-model", "messages": [{"role": "user", "content": "A test prompt"}],
        **updates,
    })


def response(**updates):
    return AIResponse.model_validate({
        "provider": "mock", "model": "example-model", "content": "Mock output", **updates,
    })


def test_valid_request_preserves_message_text_and_unspecified_parameters():
    item = request(model=" example-model ", messages=[
        {"role": "system", "content": "  Keep this spacing\n"},
        {"role": "user", "content": "Question"},
        {"role": "assistant", "content": "Answer"},
    ])
    assert item.model == "example-model"
    assert item.messages[0].content == "  Keep this spacing\n"
    assert item.temperature is None and item.max_output_tokens is None
    assert request(temperature=0, max_output_tokens=1).temperature == 0
    assert request(temperature=2).temperature == 2


@pytest.mark.parametrize("model", ["", " \n ", None, 12, True, [], "\ud800"])
def test_model_name_requires_nonblank_unicode_text(model):
    with pytest.raises(ValidationError):
        request(model=model)


@pytest.mark.parametrize("messages", [[], None, "prompt", [{"role": "tool", "content": "x"}],
    [{"role": "USER", "content": "x"}], [{"content": "x"}], [{"role": "user"}]])
def test_messages_require_nonempty_list_and_known_roles(messages):
    with pytest.raises(ValidationError):
        request(messages=messages)


@pytest.mark.parametrize("content", ["", " \n\t", None, 7, True, {}, ["text"], "\ud800"])
def test_message_content_requires_text_and_rejects_multimodal_values(content):
    with pytest.raises(ValidationError):
        AIMessage(role="user", content=content)


@pytest.mark.parametrize("value", [-0.01, 2.01, float("nan"), float("inf"), True, "0.5", {}])
def test_temperature_requires_supported_finite_numeric_range(value):
    with pytest.raises(ValidationError):
        request(temperature=value)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "512", float("inf"), []])
def test_max_output_tokens_requires_positive_integer(value):
    with pytest.raises(ValidationError):
        request(max_output_tokens=value)


def test_response_is_json_and_usage_is_optional_without_invented_counts():
    item = response(metadata={"mock": True, "details": [1, 0.5, None]}, finish_reason="stop")
    serialized = json.loads(item.model_dump_json())
    assert serialized == {
        "provider": "mock", "model": "example-model", "content": "Mock output", "finish_reason": "stop",
        "usage": None, "metadata": {"mock": True, "details": [1, 0.5, None]},
    }
    partial = response(usage={"input_tokens": 10})
    assert partial.usage == AIUsage(input_tokens=10, output_tokens=None, total_tokens=None)
    assert response(usage={}).usage == AIUsage()
    assert response(content="").content == ""


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens", "total_tokens"])
@pytest.mark.parametrize("value", [-1, True, 1.1, "10"])
def test_usage_counts_are_nullable_nonnegative_integers(field, value):
    with pytest.raises(ValidationError):
        response(usage={field: value})


@pytest.mark.parametrize("identifier", ["", " mock", "mock ", "Mock", "mock\n", "ai/model", "a" * 65, 1])
def test_provider_identifiers_have_one_exact_format(identifier):
    with pytest.raises(ValidationError):
        response(provider=identifier)


@pytest.mark.parametrize("key", ["api_key", "Authorization", "X-API-Key", "password", "client_secret", "token", "credentials"])
def test_response_metadata_does_not_admit_recognizable_credentials(key):
    with pytest.raises(ValidationError) as caught:
        response(metadata={"nested": [{key: "fixture-sensitive-value"}]})
    assert "fixture-sensitive-value" not in str(caught.value)


@pytest.mark.parametrize("metadata", [None, [], {1: "value"}, {"value": object()},
    {"value": float("nan")}, {"value": float("inf")}, {"value": (1, 2)}, {"value": "\ud800"}])
def test_metadata_requires_finite_standard_json(metadata):
    with pytest.raises(ValidationError):
        response(metadata=metadata)


def test_metadata_rejects_cycles_and_excess_depth_but_accepts_repeated_values():
    cycle = {}
    cycle["self"] = cycle
    with pytest.raises(ValidationError):
        response(metadata=cycle)
    nested = {"leaf": "value"}
    for _ in range(MAX_METADATA_DEPTH - 1):
        nested = {"nested": nested}
    assert response(metadata=nested).metadata == nested
    with pytest.raises(ValidationError):
        response(metadata={"one_more_level": nested})
    shared = {"safe": True}
    assert response(metadata={"left": shared, "right": shared}).metadata == {"left": shared, "right": shared}


def test_request_response_validation_does_not_mutate_input_or_share_defaults():
    raw = {"nested": [{"safe": "value"}]}
    expected = deepcopy(raw)
    first = response(metadata=raw)
    first.metadata["nested"][0]["safe"] = "modified"
    assert raw == expected
    default = response()
    default.metadata["safe"] = "local"
    assert response().metadata == {}


def test_prompt_and_response_are_not_in_repr_or_validation_error_text():
    marker = "fixture-prompt-response-marker"
    item = request(messages=[{"role": "user", "content": marker}])
    assert marker not in repr(item)
    assert marker not in repr(item.messages[0])
    assert marker not in repr(response(content=marker, metadata={"description": marker}))
    with pytest.raises(ValidationError) as caught:
        request(temperature=marker)
    assert marker not in str(caught.value)
    # hide_input_in_errors controls text, not explicit .errors() serialization.
    assert caught.value.errors()[0]["input"] == marker


def test_unknown_fields_and_invalid_existing_models_are_revalidated():
    with pytest.raises(ValidationError):
        request(streaming=True)
    with pytest.raises(ValidationError):
        response(http_client=object())
    bypassed = AIMessage.model_construct(role="tool", content="not text-only role")
    with pytest.raises(ValidationError):
        request(messages=[bypassed])
    caps = AIProviderCapabilities.model_construct(is_mock="true")
    with pytest.raises(ValidationError):
        AIProviderMetadata(provider_id="mock", provider_name="Mock", capabilities=caps)
