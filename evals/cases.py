"""
Evaluation Cases — Agent 回归评测集

每条用例描述一次「用户提问 → 期望的 Agent 行为」，由 runner 跑完整张图后逐条断言。
期望值全部对齐 src/services/database.py 里的演示数据，改动种子数据时需同步更新本文件。
"""
from dataclasses import dataclass, field


@dataclass
class EvalCase:
    """一条评测用例

    断言分四类，分别守住链路上的四个环节：
    路由是否正确（intent / specialist）、有没有用对工具（tools）、
    最终答得对不对（keywords）、有没有胡说（forbidden_keywords）。
    """

    id: str
    category: str              # 用例分组，用于按业务域统计通过率
    question: str              # 用户消息
    expect_intents: list       # triage 识别出的意图命中任意一个即通过
    expect_tools: list         # 这些工具都必须被调用过（可多不可少）
    expect_specialists: list   # 这些专员都必须被派到过
    expect_keywords: list      # 最终回复命中任意一个关键词即通过
    forbidden_keywords: list = field(default_factory=list)  # 最终回复里不允许出现
    note: str = ""             # 这条用例在验证什么


CASES: list[EvalCase] = [
    # ── 订单与物流 ────────────────────────────────────────────
    EvalCase(
        id="order-001",
        category="order",
        question="帮我查一下订单 ORD-1002 现在是什么状态？",
        expect_intents=["order_status", "shipping_tracking"],
        expect_tools=["lookup_order"],
        expect_specialists=["order_specialist"],
        expect_keywords=["已发货"],
        note="订单状态查询：必须查库再回答，不能凭空给状态",
    ),
    EvalCase(
        id="order-002",
        category="order",
        question="ORD-1002 的货现在到哪了？",
        expect_intents=["shipping_tracking", "order_status"],
        expect_tools=["lookup_order", "track_shipment"],
        expect_specialists=["order_specialist"],
        expect_keywords=["杭州转运中心", "运输中"],
        note="跨工具串联：先拿订单里的物流单号，再查物流位置",
    ),
    EvalCase(
        id="order-003",
        category="order",
        question="james@example.com 这个邮箱名下有哪些订单？",
        expect_intents=["order_status"],
        expect_tools=["lookup_orders_by_email"],
        expect_specialists=["order_specialist"],
        expect_keywords=["ORD-1001"],
        note="按邮箱检索：参数要走对工具，不能用订单号工具硬查",
    ),
    EvalCase(
        id="order-004",
        category="order",
        question="谁买过 Mechanical Keyboard？帮我找出来",
        expect_intents=["order_status"],
        expect_tools=["search_orders"],
        expect_specialists=["order_specialist"],
        expect_keywords=["ORD-1005"],
        note="模糊搜索：按商品名反查订单",
    ),

    # ── 退换货 ────────────────────────────────────────────────
    EvalCase(
        id="return-001",
        category="return",
        question="你们店的退货政策是怎样的？",
        expect_intents=["return_policy"],
        expect_tools=["get_return_policy"],
        expect_specialists=["return_specialist"],
        expect_keywords=["14天"],
        note="政策咨询：答案要带上真实期限，不能编",
    ),
    EvalCase(
        id="return-002",
        category="return",
        question="ORD-1001 还能退货吗？",
        expect_intents=["return_request", "return_policy"],
        expect_tools=["check_return_eligibility"],
        expect_specialists=["return_specialist"],
        expect_keywords=["符合"],
        note="退货资格判断：已送达且未超期，应给出可退结论",
    ),
    EvalCase(
        id="return-003",
        category="return",
        question="我要退 ORD-1005，帮我办理退货",
        expect_intents=["return_request"],
        expect_tools=["check_return_eligibility"],
        expect_specialists=["return_specialist"],
        expect_keywords=["过期", "不符合", "14"],
        forbidden_keywords=["已创建", "RMA-"],
        note="负例：超期订单不能创建退货单，模型必须如实告知而非硬办",
    ),
    EvalCase(
        id="return-004",
        category="return",
        question="我要退掉 ORD-1001，退款金额 600 元",
        expect_intents=["return_request"],
        expect_tools=["initiate_return"],
        expect_specialists=["return_specialist"],
        expect_keywords=["人工审核"],
        note="金额护栏：超过自动处理阈值必须转人工审核",
    ),

    # ── 闲聊 ──────────────────────────────────────────────────
    EvalCase(
        id="general-001",
        category="general",
        question="你好，你能帮我做什么？",
        expect_intents=["general"],
        expect_tools=[],
        expect_specialists=["general_specialist"],
        expect_keywords=["订单", "退货"],
        note="前台接待：不涉及业务数据，不能调用任何工具",
    ),

    # ── 混合话题（考察转接）────────────────────────────────────
    EvalCase(
        id="mixed-001",
        category="mixed",
        question="帮我查 ORD-1002 到哪了，另外这个单还能退货吗？",
        expect_intents=["shipping_tracking", "order_status", "return_request"],
        expect_tools=["lookup_order"],
        expect_specialists=["order_specialist", "return_specialist"],
        expect_keywords=["杭州转运中心", "运输中"],
        note="主管转接：一句话里两个领域，必须先后派给两个专员",
    ),

    # ── 边界与防幻觉 ──────────────────────────────────────────
    EvalCase(
        id="edge-001",
        category="edge",
        question="ORD-9999 是什么情况？帮我看看",
        expect_intents=["order_status"],
        expect_tools=["lookup_order"],
        expect_specialists=["order_specialist"],
        expect_keywords=["未找到", "没有找到", "不存在", "查不到"],
        forbidden_keywords=["已发货", "已送达", "已签收"],
        note="防幻觉：订单不存在时必须如实说没有，不能编造状态",
    ),
]
