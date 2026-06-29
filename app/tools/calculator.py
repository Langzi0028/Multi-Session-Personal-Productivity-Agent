from __future__ import annotations

import ast
import operator
from typing import Any


class CalculatorTool:
    name = "calculator"
    description = "执行基础数学计算，例如加减乘除、百分比、括号运算。"
    parameters_schema = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "数学表达式，例如 23 * 7 + 10",
            }
        },
        "required": ["expression"],
    }
    timeout = 3.0
    is_async = False
    permission = "none"

    def run(self, arguments: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        expression = arguments["expression"]
        result = _safe_eval(expression)
        return {"expression": expression, "result": result, "summary": f"{expression} = {result}"}


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(expression: str) -> int | float:
    node = ast.parse(expression, mode="eval")
    return _eval_node(node.body)


def _eval_node(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_node(node.operand))
    raise ValueError("Unsupported calculator expression")
