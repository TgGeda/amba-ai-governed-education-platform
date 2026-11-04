from __future__ import annotations

import ast
import json
import math
import operator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from amba_ai.config import DATA_DIR
from amba_ai.logger import logger


try:
    from langchain_core.tools import tool
except ImportError:
    try:
        from langchain_community.tools import tool
    except ImportError:

        def tool(
            name: str | Callable[..., Any] | None = None,
            *args: Any,
            **kwargs: Any,
        ) -> Callable[..., Any]:
            if callable(name):
                fn = name
                setattr(fn, "name", fn.__name__)
                setattr(fn, "description", fn.__doc__ or "")
                setattr(fn, "run", fn)
                return fn

            def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
                setattr(fn, "name", name or fn.__name__)
                setattr(fn, "description", fn.__doc__ or "")
                setattr(fn, "run", fn)
                return fn

            return decorator


SCHEDULE_PATH = DATA_DIR / "db" / "study_schedule.json"

MAX_EXPRESSION_LENGTH = 256
MAX_AST_NODES = 128
MAX_AST_DEPTH = 32
MAX_ABS_RESULT = 1e12
MAX_POWER_EXPONENT = 20
MAX_ROUND_DIGITS = 15
MAX_FUNCTION_ARGS = 4
MAX_SCHEDULE_FILE_BYTES = 5_000_000

BinaryFunction = Callable[[float, float], float]
UnaryFunction = Callable[[float], float]
MathFunction = Callable[..., float]
ArgumentValidator = Callable[[list[float]], None]


_ALLOWED_BINARY_OPERATORS: dict[type[ast.operator], BinaryFunction] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_ALLOWED_UNARY_OPERATORS: dict[type[ast.unaryop], UnaryFunction] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_ALLOWED_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}


@dataclass(frozen=True, slots=True)
class FunctionSpec:
    function: MathFunction
    min_args: int
    max_args: int
    validator: ArgumentValidator | None = None


class MathEvaluationError(ValueError):
    pass


class MathSyntaxError(MathEvaluationError):
    pass


class MathDomainError(MathEvaluationError):
    pass


class MathLimitError(MathEvaluationError):
    pass


def _cbrt(value: float) -> float:
    if hasattr(math, "cbrt"):
        return float(math.cbrt(value))

    if value == 0:
        return 0.0

    return math.copysign(abs(value) ** (1.0 / 3.0), value)


def _safe_round(value: float, digits: float = 0.0) -> float:
    if not digits.is_integer():
        raise ValueError("The round precision must be an integer.")

    if abs(digits) > MAX_ROUND_DIGITS:
        raise ValueError(
            f"The round precision cannot exceed {MAX_ROUND_DIGITS} digits."
        )

    return float(round(value, int(digits)))


def _validate_non_negative_first_argument(args: list[float]) -> None:
    if args[0] < 0:
        raise ValueError("The first argument must be non-negative.")


def _validate_log_arguments(args: list[float]) -> None:
    if args[0] <= 0:
        raise ValueError("Logarithms require a positive value.")

    if len(args) == 2:
        base = args[1]

        if base <= 0:
            raise ValueError("The logarithm base must be positive.")

        if base == 1:
            raise ValueError("The logarithm base cannot equal one.")


def _validate_unit_interval(args: list[float]) -> None:
    if not -1 <= args[0] <= 1:
        raise ValueError("The argument must be between -1 and 1.")


def _validate_acosh_arguments(args: list[float]) -> None:
    if args[0] < 1:
        raise ValueError(
            "acosh requires an argument greater than or equal to 1."
        )


def _validate_atanh_arguments(args: list[float]) -> None:
    if not -1 < args[0] < 1:
        raise ValueError(
            "atanh requires an argument strictly between -1 and 1."
        )


_ALLOWED_FUNCTIONS: dict[str, FunctionSpec] = {
    "abs": FunctionSpec(abs, 1, 1),
    "round": FunctionSpec(_safe_round, 1, 2),
    "sqrt": FunctionSpec(
        math.sqrt,
        1,
        1,
        _validate_non_negative_first_argument,
    ),
    "cbrt": FunctionSpec(_cbrt, 1, 1),
    "sin": FunctionSpec(math.sin, 1, 1),
    "cos": FunctionSpec(math.cos, 1, 1),
    "tan": FunctionSpec(math.tan, 1, 1),
    "asin": FunctionSpec(math.asin, 1, 1, _validate_unit_interval),
    "acos": FunctionSpec(math.acos, 1, 1, _validate_unit_interval),
    "atan": FunctionSpec(math.atan, 1, 1),
    "atan2": FunctionSpec(math.atan2, 2, 2),
    "sinh": FunctionSpec(math.sinh, 1, 1),
    "cosh": FunctionSpec(math.cosh, 1, 1),
    "tanh": FunctionSpec(math.tanh, 1, 1),
    "asinh": FunctionSpec(math.asinh, 1, 1),
    "acosh": FunctionSpec(
        math.acosh,
        1,
        1,
        _validate_acosh_arguments,
    ),
    "atanh": FunctionSpec(
        math.atanh,
        1,
        1,
        _validate_atanh_arguments,
    ),
    "rad": FunctionSpec(math.radians, 1, 1),
    "radians": FunctionSpec(math.radians, 1, 1),
    "deg": FunctionSpec(math.degrees, 1, 1),
    "degrees": FunctionSpec(math.degrees, 1, 1),
    "log": FunctionSpec(math.log, 1, 2, _validate_log_arguments),
    "ln": FunctionSpec(math.log, 1, 1, _validate_log_arguments),
    "log2": FunctionSpec(math.log2, 1, 1, _validate_log_arguments),
    "log10": FunctionSpec(math.log10, 1, 1, _validate_log_arguments),
    "exp": FunctionSpec(math.exp, 1, 1),
    "floor": FunctionSpec(math.floor, 1, 1),
    "ceil": FunctionSpec(math.ceil, 1, 1),
    "hypot": FunctionSpec(math.hypot, 2, MAX_FUNCTION_ARGS),
}


def _validate_result(value: float) -> None:
    if not math.isfinite(value):
        raise MathLimitError("The result is not finite.")

    if abs(value) > MAX_ABS_RESULT:
        raise MathLimitError("The result exceeds the permitted magnitude.")


def _validate_ast_complexity(tree: ast.AST) -> None:
    node_count = sum(1 for _ in ast.walk(tree))

    if node_count > MAX_AST_NODES:
        raise MathLimitError("The expression is too complex.")

    stack: list[tuple[ast.AST, int]] = [(tree, 1)]

    while stack:
        node, depth = stack.pop()

        if depth > MAX_AST_DEPTH:
            raise MathLimitError("The expression is nested too deeply.")

        for child in ast.iter_child_nodes(node):
            stack.append((child, depth + 1))


def _normalize_expression(expression: str) -> str:
    return expression.replace("^", "**")


def _evaluate_binary_operation(node: ast.BinOp) -> float:
    operator_type = type(node.op)

    if operator_type not in _ALLOWED_BINARY_OPERATORS:
        raise MathSyntaxError("The binary operator is not supported.")

    left = _safe_eval(node.left)
    right = _safe_eval(node.right)

    if operator_type in {ast.Div, ast.FloorDiv, ast.Mod} and right == 0:
        raise ZeroDivisionError("Division by zero.")

    if operator_type is ast.Pow:
        if abs(right) > MAX_POWER_EXPONENT:
            raise MathLimitError("The exponent exceeds the permitted limit.")

        if left < 0 and not right.is_integer():
            raise MathDomainError(
                "A negative base cannot have a fractional exponent."
            )

        if left == 0 and right < 0:
            raise ZeroDivisionError(
                "Zero cannot be raised to a negative exponent."
            )

        if abs(left) > 1:
            estimated_magnitude = right * math.log10(abs(left))

            if estimated_magnitude > math.log10(MAX_ABS_RESULT):
                raise MathLimitError(
                    "The result exceeds the permitted magnitude."
                )

    operation = _ALLOWED_BINARY_OPERATORS[operator_type]

    try:
        result = float(operation(left, right))
    except ZeroDivisionError:
        raise
    except OverflowError as exc:
        raise MathLimitError("The operation overflowed.") from exc
    except (TypeError, ValueError) as exc:
        raise MathDomainError(
            "The operation is undefined for the supplied values."
        ) from exc

    _validate_result(result)
    return result


def _evaluate_unary_operation(node: ast.UnaryOp) -> float:
    operator_type = type(node.op)

    if operator_type not in _ALLOWED_UNARY_OPERATORS:
        raise MathSyntaxError("The unary operator is not supported.")

    operand = _safe_eval(node.operand)
    operation = _ALLOWED_UNARY_OPERATORS[operator_type]

    try:
        result = float(operation(operand))
    except OverflowError as exc:
        raise MathLimitError("The unary operation overflowed.") from exc
    except (TypeError, ValueError) as exc:
        raise MathDomainError(
            "The unary operation is undefined for this value."
        ) from exc

    _validate_result(result)
    return result


def _evaluate_function_call(node: ast.Call) -> float:
    if not isinstance(node.func, ast.Name):
        raise MathSyntaxError(
            "Only direct calls to approved functions are allowed."
        )

    if node.keywords:
        raise MathSyntaxError("Keyword arguments are not allowed.")

    function_name = node.func.id.lower()
    function_spec = _ALLOWED_FUNCTIONS.get(function_name)

    if function_spec is None:
        raise MathSyntaxError(
            f"The function '{function_name}' is not supported."
        )

    argument_count = len(node.args)

    if not function_spec.min_args <= argument_count <= function_spec.max_args:
        if function_spec.min_args == function_spec.max_args:
            expected = str(function_spec.min_args)
        else:
            expected = (
                f"{function_spec.min_args} to {function_spec.max_args}"
            )

        raise MathSyntaxError(
            f"The function '{function_name}' expects "
            f"{expected} argument(s)."
        )

    arguments = [_safe_eval(argument) for argument in node.args]

    if function_spec.validator is not None:
        try:
            function_spec.validator(arguments)
        except ValueError as exc:
            raise MathDomainError(str(exc)) from exc

    try:
        result = float(function_spec.function(*arguments))
    except ZeroDivisionError:
        raise
    except OverflowError as exc:
        raise MathLimitError(
            f"The function '{function_name}' overflowed."
        ) from exc
    except (TypeError, ValueError) as exc:
        raise MathDomainError(
            f"The function '{function_name}' is undefined "
            "for the supplied arguments."
        ) from exc

    _validate_result(result)
    return result


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise MathSyntaxError("Boolean values are not allowed.")

        if not isinstance(node.value, (int, float)):
            raise MathSyntaxError("Only numeric constants are allowed.")

        value = float(node.value)
        _validate_result(value)
        return value

    if isinstance(node, ast.Num):
        value = float(node.n)
        _validate_result(value)
        return value

    if isinstance(node, ast.Name):
        constant_name = node.id.lower()

        if constant_name not in _ALLOWED_CONSTANTS:
            raise MathSyntaxError(
                f"The symbol '{node.id}' is not supported."
            )

        value = float(_ALLOWED_CONSTANTS[constant_name])
        _validate_result(value)
        return value

    if isinstance(node, ast.BinOp):
        return _evaluate_binary_operation(node)

    if isinstance(node, ast.UnaryOp):
        return _evaluate_unary_operation(node)

    if isinstance(node, ast.Call):
        return _evaluate_function_call(node)

    raise MathSyntaxError(
        f"The expression element '{type(node).__name__}' is not allowed."
    )


def _format_number(value: float) -> str:
    if value == 0:
        return "0"

    if value.is_integer():
        return str(int(value))

    return f"{value:.12g}"


@tool("calculate_math")
def calculate_math(expression: str) -> str:
    """
    Safely evaluate an offline mathematical expression using approved
    operators, constants, and real-number functions.
    """
    if not isinstance(expression, str) or not expression.strip():
        return "Error: Expression cannot be empty."

    clean_expression = expression.strip()

    if len(clean_expression) > MAX_EXPRESSION_LENGTH:
        return (
            "Error: Expression exceeds the maximum length of "
            f"{MAX_EXPRESSION_LENGTH} characters."
        )

    try:
        normalized_expression = _normalize_expression(clean_expression)
        tree = ast.parse(normalized_expression, mode="eval")
        _validate_ast_complexity(tree)
        result = _safe_eval(tree)
        return _format_number(result)

    except SyntaxError as exc:
        logger.info(
            "Math expression contained invalid syntax",
            extra={
                "context": {
                    "expression": clean_expression[:MAX_EXPRESSION_LENGTH],
                    "error_type": type(exc).__name__,
                }
            },
        )
        return "Error: Invalid mathematical syntax."

    except ZeroDivisionError:
        return "Error: Division by zero is not allowed."

    except MathLimitError as exc:
        logger.info(
            "Math expression exceeded a safety limit",
            extra={
                "context": {
                    "expression": clean_expression[:MAX_EXPRESSION_LENGTH],
                    "error": str(exc),
                }
            },
        )
        return "Error: The calculation exceeds the permitted safety limits."

    except MathDomainError as exc:
        logger.info(
            "Math expression contained an invalid domain value",
            extra={
                "context": {
                    "expression": clean_expression[:MAX_EXPRESSION_LENGTH],
                    "error": str(exc),
                }
            },
        )
        return "Error: The calculation is undefined for the supplied values."

    except MathSyntaxError as exc:
        logger.info(
            "Math expression used an unsupported construct",
            extra={
                "context": {
                    "expression": clean_expression[:MAX_EXPRESSION_LENGTH],
                    "error": str(exc),
                }
            },
        )
        return "Error: Invalid or unsupported mathematical expression."

    except Exception as exc:
        logger.exception(
            "Unexpected math tool failure",
            extra={
                "context": {
                    "expression": clean_expression[:MAX_EXPRESSION_LENGTH],
                    "error": str(exc),
                }
            },
        )
        return "Error: Unable to evaluate the mathematical expression."


def _parse_due_timestamp(raw_value: Any) -> datetime:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError("next_due must be a non-empty string.")

    normalized_value = raw_value.strip()

    if normalized_value.endswith(("Z", "z")):
        normalized_value = normalized_value[:-1] + "+00:00"

    due_at = datetime.fromisoformat(normalized_value)

    if due_at.tzinfo is None or due_at.utcoffset() is None:
        raise ValueError("next_due must include timezone information.")

    return due_at.astimezone(timezone.utc)


def _count_due_flashcards(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0

    if not path.is_file():
        raise ValueError("The study schedule path is not a regular file.")

    if path.stat().st_size > MAX_SCHEDULE_FILE_BYTES:
        raise ValueError(
            "The study schedule exceeds the maximum permitted size."
        )

    with path.open("r", encoding="utf-8") as schedule_file:
        payload = json.load(schedule_file)

    if not isinstance(payload, dict):
        raise ValueError(
            "The study schedule root must be a JSON object."
        )

    now = datetime.now(timezone.utc)
    due_count = 0
    total_count = 0

    for card_id, raw_record in payload.items():
        total_count += 1

        if not isinstance(raw_record, dict):
            due_count += 1
            logger.warning(
                "Malformed flashcard record counted as due",
                extra={
                    "context": {
                        "card_id": str(card_id),
                        "record_type": type(raw_record).__name__,
                    }
                },
            )
            continue

        raw_due = raw_record.get("next_due")

        if raw_due is None or raw_due == "":
            due_count += 1
            continue

        try:
            due_at = _parse_due_timestamp(raw_due)
        except (TypeError, ValueError) as exc:
            due_count += 1
            logger.warning(
                "Malformed flashcard timestamp counted as due",
                extra={
                    "context": {
                        "card_id": str(card_id),
                        "error": str(exc),
                    }
                },
            )
            continue

        if due_at <= now:
            due_count += 1

    return due_count, total_count


@tool("check_due_flashcards")
def check_due_flashcards() -> str:
    """
    Return current flashcard review metrics from the local study schedule.
    """
    try:
        due_count, total_count = _count_due_flashcards(SCHEDULE_PATH)

        if total_count == 0:
            return "No flashcards are currently scheduled."

        if due_count == 0:
            return (
                f"You're all caught up. All {total_count} flashcards "
                "are up to date."
            )

        if due_count == 1:
            return (
                f"1 of {total_count} flashcards is due for review right now."
            )

        return (
            f"{due_count} of {total_count} flashcards are due "
            "for review right now."
        )

    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.error(
            "Failed to read the local flashcard schedule",
            extra={
                "context": {
                    "schedule_path": str(SCHEDULE_PATH),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            },
            exc_info=True,
        )
        return (
            "Error: Unable to determine due flashcards from "
            "the local schedule store."
        )

    except Exception as exc:
        logger.exception(
            "Unexpected flashcard schedule failure",
            extra={
                "context": {
                    "schedule_path": str(SCHEDULE_PATH),
                    "error": str(exc),
                }
            },
        )
        return (
            "Error: Unable to determine due flashcards from "
            "the local schedule store."
        )


@tool("get_local_time")
def get_local_time() -> str:
    """
    Return the host system's current local time and timezone.
    """
    now = datetime.now().astimezone()
    return now.strftime("%A, %B %d, %Y, %I:%M:%S %p %Z")


@tool("get_utc_time")
def get_utc_time() -> str:
    """
    Return the current UTC time in ISO 8601 format.
    """
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_local_tools() -> list[Callable[..., Any]]:
    return [
        calculate_math,
        check_due_flashcards,
        get_local_time,
        get_utc_time,
    ]


def get_tool_registry() -> dict[str, Callable[..., Any]]:
    registry: dict[str, Callable[..., Any]] = {}

    for local_tool in get_local_tools():
        tool_name = (
            getattr(local_tool, "name", None)
            or getattr(local_tool, "__name__", None)
        )

        if not tool_name:
            logger.warning(
                "Skipping local tool without a discoverable name",
                extra={
                    "context": {
                        "tool_type": type(local_tool).__name__,
                    }
                },
            )
            continue

        normalized_name = str(tool_name)

        if normalized_name in registry:
            raise ValueError(
                f"Duplicate local tool name: {normalized_name}"
            )

        registry[normalized_name] = local_tool

    return registry


LOCAL_TOOLS = get_local_tools()
TOOL_REGISTRY = get_tool_registry()