"""Tests for the argument-coercion primitives every batch handler shares.

These helpers were extracted from ``batch.application.batch_handlers``
in #114 and gained ``default=`` overloads in #121.  Per-feature
handler tests cover the happy paths indirectly, but the helpers
themselves are a public utility surface and deserve direct
specification — both to document the contract and to lock in the
strict-validation behaviour (e.g. a string ``"true"`` from a
hand-edited JSON payload must NOT silently coerce to ``True``).
"""

from __future__ import annotations

import pytest

from flstudio_cli.shared.application.handler_args import (
    optional_bool,
    optional_int,
    optional_string,
    require,
    require_bool,
    require_float,
    require_int,
    require_string,
)


class TestRequire:
    def test_given_present_key_when_require_then_returns_raw_value(self) -> None:
        assert require({"a": "x"}, "a") == "x"

    def test_given_present_key_with_none_value_when_require_then_returns_none(
        self,
    ) -> None:
        # ``require`` only cares about presence, not value.
        assert require({"a": None}, "a") is None

    def test_given_missing_key_when_require_then_raises_with_key_in_message(
        self,
    ) -> None:
        with pytest.raises(ValueError, match="missing required argument: 'a'"):
            require({}, "a")


class TestRequireString:
    def test_given_string_value_when_require_string_then_returns_it(self) -> None:
        assert require_string({"name": "kick"}, "name") == "kick"

    @pytest.mark.parametrize("bad", [42, 1.5, True, None, ["x"], {"k": "v"}])
    def test_given_non_string_value_when_require_string_then_raises(
        self, bad: object
    ) -> None:
        with pytest.raises(TypeError, match="must be a string"):
            require_string({"name": bad}, "name")

    def test_given_missing_key_when_require_string_then_raises_missing(self) -> None:
        with pytest.raises(ValueError, match="missing required argument"):
            require_string({}, "name")


class TestRequireInt:
    def test_given_int_value_when_require_int_then_returns_it(self) -> None:
        assert require_int({"n": 7}, "n") == 7

    def test_given_float_value_when_require_int_then_truncates(self) -> None:
        # JSON numbers may arrive as float; require_int coerces.
        assert require_int({"n": 7.9}, "n") == 7

    def test_given_bool_value_when_require_int_then_raises(self) -> None:
        # bool is a Python int subclass; the helper rejects it strictly so a
        # JSON ``true`` does not silently become 1.
        with pytest.raises(TypeError, match="must be a number"):
            require_int({"n": True}, "n")

    @pytest.mark.parametrize("bad", ["7", None, [7], {"n": 7}])
    def test_given_non_numeric_value_when_require_int_then_raises(
        self, bad: object
    ) -> None:
        with pytest.raises(TypeError, match="must be a number"):
            require_int({"n": bad}, "n")


class TestRequireFloat:
    def test_given_int_value_when_require_float_then_returns_float(self) -> None:
        assert require_float({"x": 7}, "x") == 7.0
        assert isinstance(require_float({"x": 7}, "x"), float)

    def test_given_float_value_when_require_float_then_returns_it(self) -> None:
        assert require_float({"x": 1.5}, "x") == 1.5

    def test_given_bool_value_when_require_float_then_raises(self) -> None:
        with pytest.raises(TypeError, match="must be a number"):
            require_float({"x": False}, "x")

    @pytest.mark.parametrize("bad", ["1.5", None])
    def test_given_non_numeric_value_when_require_float_then_raises(
        self, bad: object
    ) -> None:
        with pytest.raises(TypeError, match="must be a number"):
            require_float({"x": bad}, "x")


class TestRequireBool:
    """require_bool is strict: a string ``"true"`` must NOT coerce to True.

    Hand-edited JSON files are the threat model — a typo there should
    surface as a typed error, not a silent miscoercion.
    """

    @pytest.mark.parametrize("value", [True, False])
    def test_given_bool_value_when_require_bool_then_returns_it(
        self, value: bool
    ) -> None:
        assert require_bool({"on": value}, "on") is value

    @pytest.mark.parametrize("bad", [1, 0, "true", "false", "yes", None, []])
    def test_given_non_bool_value_when_require_bool_then_raises(
        self, bad: object
    ) -> None:
        with pytest.raises(TypeError, match="must be a boolean"):
            require_bool({"on": bad}, "on")

    def test_given_missing_key_when_require_bool_then_raises_missing(self) -> None:
        with pytest.raises(ValueError, match="missing required argument"):
            require_bool({}, "on")


class TestOptionalIntDefaults:
    def test_given_present_key_when_optional_int_then_returns_value(self) -> None:
        assert optional_int({"n": 5}, "n") == 5

    def test_given_missing_key_and_no_default_when_optional_int_then_returns_none(
        self,
    ) -> None:
        assert optional_int({}, "n") is None

    def test_given_missing_key_and_default_when_optional_int_then_returns_default(
        self,
    ) -> None:
        assert optional_int({}, "n", default=42) == 42

    def test_given_present_key_and_default_when_optional_int_then_returns_value(
        self,
    ) -> None:
        # The default only applies when the key is absent — present values
        # always win, even if equal to the default.
        assert optional_int({"n": 5}, "n", default=42) == 5

    def test_given_present_invalid_value_when_optional_int_then_still_validates(
        self,
    ) -> None:
        # default= does not bypass type validation when the key IS present.
        with pytest.raises(TypeError, match="must be a number"):
            optional_int({"n": "bad"}, "n", default=42)


class TestOptionalStringDefaults:
    def test_given_missing_key_when_optional_string_then_returns_none(self) -> None:
        assert optional_string({}, "name") is None

    def test_given_missing_key_and_default_when_optional_string_then_returns_default(
        self,
    ) -> None:
        assert optional_string({}, "name", default="anon") == "anon"

    def test_given_present_key_when_optional_string_then_returns_value(self) -> None:
        assert optional_string({"name": "x"}, "name", default="anon") == "x"

    def test_given_present_invalid_value_when_optional_string_then_validates(
        self,
    ) -> None:
        with pytest.raises(TypeError, match="must be a string"):
            optional_string({"name": 42}, "name", default="anon")


class TestOptionalBoolDefaults:
    def test_given_missing_key_when_optional_bool_then_returns_none(self) -> None:
        assert optional_bool({}, "on") is None

    def test_given_missing_key_and_default_when_optional_bool_then_returns_default(
        self,
    ) -> None:
        assert optional_bool({}, "on", default=True) is True

    @pytest.mark.parametrize("value", [True, False])
    def test_given_present_bool_when_optional_bool_then_returns_value(
        self, value: bool
    ) -> None:
        assert optional_bool({"on": value}, "on", default=True) is value

    def test_given_present_invalid_value_when_optional_bool_then_validates(
        self,
    ) -> None:
        with pytest.raises(TypeError, match="must be a boolean"):
            optional_bool({"on": "yes"}, "on", default=True)
