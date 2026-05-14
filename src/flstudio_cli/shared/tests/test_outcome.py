"""Tests for the Outcome (Ok / Err) chain methods.

The chain methods replace ``isinstance(result, Ok)`` ladders at call
sites. Each variant must short-circuit appropriately: ``Ok`` propagates
through ``map`` / ``flat_map`` and ignores ``map_err``; ``Err`` does the
opposite.
"""

from __future__ import annotations

from flstudio_cli.shared.utility.outcome import Err, Ok


class TestOkChain:
    def test_map_transforms_value_and_keeps_ok_variant(self):
        result = Ok(2).map(lambda x: x * 3)
        assert isinstance(result, Ok)
        assert result.value == 6

    def test_flat_map_threads_value_into_next_outcome(self):
        result = Ok(4).flat_map(lambda x: Ok(x + 1))
        assert isinstance(result, Ok)
        assert result.value == 5

    def test_flat_map_can_short_circuit_to_err(self):
        result = Ok(4).flat_map(lambda _x: Err("downstream"))
        assert isinstance(result, Err)
        assert result.error == "downstream"

    def test_map_err_is_a_no_op_on_ok(self):
        original = Ok(7)
        result = original.map_err(lambda _e: "should not run")
        assert result is original

    def test_unwrap_or_returns_value_and_ignores_default(self):
        assert Ok(42).unwrap_or(0) == 42

    def test_is_ok_is_true(self):
        assert Ok(1).is_ok() is True


class TestErrChain:
    def test_map_is_a_no_op_on_err(self):
        original: Err[str] = Err("boom")
        result = original.map(lambda x: x * 3)
        assert result is original

    def test_flat_map_is_a_no_op_on_err(self):
        original: Err[str] = Err("boom")
        result = original.flat_map(lambda x: Ok(x + 1))
        assert result is original

    def test_map_err_transforms_error_and_keeps_err_variant(self):
        result: Ok[int] | Err[str] = Err(404).map_err(lambda code: f"http {code}")
        assert isinstance(result, Err)
        assert result.error == "http 404"

    def test_unwrap_or_returns_default(self):
        assert Err("boom").unwrap_or(99) == 99

    def test_is_ok_is_false(self):
        assert Err("boom").is_ok() is False


class TestChainComposition:
    def test_chained_ok_pipeline_threads_through(self):
        # parse -> validate -> format style pipeline
        result = (
            Ok("42")
            .map(int)
            .flat_map(lambda n: Ok(n) if n >= 0 else Err("negative"))
            .map(lambda n: f"value={n}")
        )
        assert isinstance(result, Ok)
        assert result.value == "value=42"

    def test_first_err_short_circuits_remaining_chain(self):
        seen: list[str] = []

        def record_then_double(x: int) -> int:
            seen.append("doubled")
            return x * 2

        result = (
            Err("bad input")
            .map(record_then_double)
            .flat_map(lambda x: Ok(x + 1))
            .map(record_then_double)
        )

        assert isinstance(result, Err)
        assert result.error == "bad input"
        assert seen == []
