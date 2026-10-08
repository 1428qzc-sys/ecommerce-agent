"""
Evaluation Runner — 逐条执行评测集并打分

评测走的是完整链路（triage → supervisor → 专员 → response），
因此每条用例的结论都是端到端的：路由、派单、工具、答案四项一起验。

用法：
    python -m evals.runner                    # 跑全部用例
    python -m evals.runner --category order   # 只跑某一类
    python -m evals.runner --verbose          # 打印每条的实际回复，便于排查
"""
import argparse
import logging
import sys
from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage

from src.agent.graph import build_graph
from src.services.database import init_db
from evals.cases import CASES

logger = logging.getLogger(__name__)

# 通过率低于该值则判定本次评测不通过（供 CI 门禁使用）
PASS_THRESHOLD = 0.8


@dataclass
class CaseResult:
    """单条用例的执行结果与四项断言结论"""

    case_id: str
    category: str
    intent_ok: bool
    tools_ok: bool
    specialists_ok: bool
    keyword_ok: bool
    forbidden_ok: bool
    # 实际跑出来的值，失败时用于定位问题
    actual_intent: str = ""
    actual_tools: list = field(default_factory=list)
    actual_specialists: list = field(default_factory=list)
    actual_answer: str = ""
    failed_reasons: list = field(default_factory=list)
    error: str = ""

    @property
    def passed(self) -> bool:
        """四项断言全绿才算通过；执行异常直接记为失败"""
        if self.error:
            return False
        return all([
            self.intent_ok, self.tools_ok,
            self.specialists_ok, self.keyword_ok, self.forbidden_ok,
        ])


def build_initial_state(question: str) -> dict:
    """构造一次评测的初始状态，字段与线上 /chat 的入参保持一致"""
    return {
        "messages": [HumanMessage(content=question)],
        "intent": "",
        "order_id": "",
        "tracking_number": "",
        "customer_email": "",
        "tool_results": {},
        "specialist_replies": [],
        "final_response": "",
        "retry_count": 0,
        "next": "",
        "task": "",
        "handoff_count": 0,
        "dispatched": [],
        "error_message": None,
    }


def collect_tool_names(messages: list) -> list:
    """从消息历史里收集模型实际请求过的工具名

    取的是模型决策（AIMessage.tool_calls），而不是工具节点执行后的回执，
    因为「选了哪个工具」才是行为断言要验的东西。
    """
    names = []
    for msg in messages:
        for call in getattr(msg, "tool_calls", None) or []:
            tool_name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if tool_name:
                names.append(tool_name)
    return names


def check_expected_subset(expected: list, actual: list) -> bool:
    """期望集合必须是实际集合的子集：允许多调，不允许漏调"""
    return set(expected).issubset(set(actual))


def check_any_keyword(keywords: list, answer: str) -> bool:
    """答案里命中任意一个关键词即通过

    用「任一命中」而不是精确匹配，是为了容忍措辞差异
    （"运输中" 与 "已在运输途中" 都算对），同时关键事实一个都不能少。
    """
    if not keywords:
        return True
    return any(k in answer for k in keywords)


def run_case(graph, case) -> CaseResult:
    """跑一条用例，返回四项断言的结论"""
    try:
        result = graph.invoke(build_initial_state(case.question))
    except Exception as e:
        logger.error("Case %s crashed: %s", case.id, e)
        return CaseResult(
            case_id=case.id, category=case.category,
            intent_ok=False, tools_ok=False, specialists_ok=False,
            keyword_ok=False, forbidden_ok=False,
            failed_reasons=[f"执行异常：{e}"], error=str(e),
        )

    messages = result.get("messages", [])
    actual_intent = result.get("intent", "")
    actual_tools = collect_tool_names(messages)
    actual_specialists = result.get("dispatched", [])
    # 以 final_response 为准：它就是用户最终看到的内容
    actual_answer = result.get("final_response", "")

    intent_ok = actual_intent in case.expect_intents
    tools_ok = check_expected_subset(case.expect_tools, actual_tools)
    specialists_ok = check_expected_subset(case.expect_specialists, actual_specialists)
    keyword_ok = check_any_keyword(case.expect_keywords, actual_answer)
    forbidden_ok = not any(k in actual_answer for k in case.forbidden_keywords)

    reasons = []
    if not intent_ok:
        reasons.append(f"意图不符（期望 {case.expect_intents} 之一，实际 {actual_intent}）")
    if not tools_ok:
        reasons.append(f"工具漏调（期望含 {case.expect_tools}，实际 {sorted(set(actual_tools))}）")
    if not specialists_ok:
        reasons.append(f"派单不符（期望含 {case.expect_specialists}，实际 {actual_specialists}）")
    if not keyword_ok:
        reasons.append(f"答案缺关键词（期望命中 {case.expect_keywords} 之一）")
    if not forbidden_ok:
        reasons.append(f"答案出现了不允许的内容（{case.forbidden_keywords}）")

    return CaseResult(
        case_id=case.id, category=case.category,
        intent_ok=intent_ok, tools_ok=tools_ok, specialists_ok=specialists_ok,
        keyword_ok=keyword_ok, forbidden_ok=forbidden_ok,
        actual_intent=actual_intent, actual_tools=actual_tools,
        actual_specialists=actual_specialists, actual_answer=actual_answer,
        failed_reasons=reasons,
    )


def print_report(results: list, verbose: bool) -> float:
    """打印逐条结果与汇总，返回本次通过率"""
    print("\n" + "=" * 72)
    print(f"{'用例':<14}{ '分类':<10}{'结果':<6}说明")
    print("=" * 72)

    for r in results:
        flag = "PASS" if r.passed else "FAIL"
        detail = " / ".join(r.failed_reasons) if r.failed_reasons else "—"
        print(f"{r.case_id:<14}{r.category:<10}{flag:<6}{detail}")
        if verbose:
            print(f"{'':<14}实际意图：{r.actual_intent}")
            print(f"{'':<14}实际工具：{sorted(set(r.actual_tools))}")
            print(f"{'':<14}实际派单：{r.actual_specialists}")
            answer = r.actual_answer.replace("\n", " ")
            print(f"{'':<14}实际回复：{answer[:120]}")

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    rate = passed / total if total else 0.0

    print("=" * 72)
    print(f"通过 {passed}/{total}，通过率 {rate:.0%}")

    # 按业务域统计：定位是哪个环节在拖后腿
    by_category = {}
    for r in results:
        stat = by_category.setdefault(r.category, [0, 0])
        stat[1] += 1
        if r.passed:
            stat[0] += 1
    print("—— 分类统计 ——")
    for category, (ok, cnt) in sorted(by_category.items()):
        print(f"  {category:<10}{ok}/{cnt}")
    print("=" * 72 + "\n")

    return rate


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 Agent 评测集")
    parser.add_argument("--category", default="", help="只跑指定分类，如 order / return / edge")
    parser.add_argument("--threshold", type=float, default=PASS_THRESHOLD, help="通过率下限")
    parser.add_argument("--verbose", action="store_true", help="打印每条用例的实际输出")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    # 评测依赖演示数据，先确保库已建好并灌入种子
    init_db()
    graph = build_graph()

    cases = [c for c in CASES if not args.category or c.category == args.category]
    if not cases:
        print(f"没有匹配分类「{args.category}」的用例")
        return 1

    print(f"开始评测：{len(cases)} 条用例（会真实调用模型，请耐心等待）")
    results = []
    for case in cases:
        logger.info("Running case %s", case.id)
        result = run_case(graph, case)
        results.append(result)
        print(f"  [{len(results)}/{len(cases)}] {case.id} {'PASS' if result.passed else 'FAIL'}")

    rate = print_report(results, args.verbose)

    if rate < args.threshold:
        print(f"❌ 通过率 {rate:.0%} 低于下限 {args.threshold:.0%}，本次评测不通过")
        return 1
    print(f"✅ 通过率 {rate:.0%} 达到下限 {args.threshold:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
