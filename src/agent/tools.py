"""
Agent Tools — LLM 可调用的工具定义
每个 @tool 的 docstring 会被 LLM 读取，用于决定何时调用该工具
"""
from langchain_core.tools import tool
from src.services.order_service import OrderService, order_status_text
from src.services.shipping_service import ShippingService, shipment_status_text
from src.services.returns_service import ReturnsService, return_status_text


@tool
def lookup_order(order_id: str) -> str:
    """根据订单号查询订单详情，返回客户姓名、状态、商品、总金额和物流单号。"""
    svc = OrderService()
    order = svc.get_order(order_id)
    if not order:
        return f"订单 {order_id} 未找到。"
    items_str = ", ".join(f"{i.product_name} x{i.quantity}（¥{i.price:.2f}）" for i in order.items)
    # 顺带查出这张订单对应的物流单号：用户追问"货到哪了"时可以接着用 track_shipment 查询
    shipment = ShippingService().track_by_order(order_id)
    shipment_str = f" | 物流单号：{shipment.tracking_number}（{shipment.carrier}）" if shipment else ""
    return (
        f"订单 {order.order_id} | 客户：{order.customer_name}（{order.email}）| "
        f"状态：{order_status_text(order.status)} | 商品：{items_str} | 总计：¥{order.total:.2f}"
        f"{shipment_str}"
    )


@tool
def lookup_orders_by_email(email: str) -> str:
    """根据客户邮箱查询该客户的所有订单。"""
    svc = OrderService()
    orders = svc.get_orders_by_email(email)
    if not orders:
        return f"未找到 {email} 的订单。"
    lines = [f"找到 {len(orders)} 个订单："]
    for o in orders:
        lines.append(
            f"  - {o.order_id}：{order_status_text(o.status)}，¥{o.total:.2f}（{len(o.items)} 件商品）"
        )
    return "\n".join(lines)


@tool
def search_orders(keyword: str) -> str:
    """按客户姓名或商品名称模糊搜索订单。"""
    svc = OrderService()
    results = svc.search_orders(keyword)
    if not results:
        return f"未找到匹配 '{keyword}' 的订单。"
    lines = [f"找到 {len(results)} 个匹配 '{keyword}' 的订单："]
    for o in results:
        lines.append(f"  - {o.order_id}（{o.customer_name}）：{order_status_text(o.status)}，¥{o.total:.2f}")
    return "\n".join(lines)


@tool
def track_shipment(tracking_number: str) -> str:
    """根据物流单号查询物流信息，返回承运商、状态和位置。"""
    svc = ShippingService()
    shipment = svc.track(tracking_number)
    if not shipment:
        return f"物流单号 {tracking_number} 未找到。"
    return (
        f"物流：{shipment.tracking_number} | 承运商：{shipment.carrier} | "
        f"状态：{shipment_status_text(shipment.status)} | 位置：{shipment.location}"
    )


@tool
def get_return_policy() -> str:
    """获取店铺退货政策详情。"""
    svc = ReturnsService()
    return svc.get_policy()


@tool
def check_return_eligibility(order_id: str) -> str:
    """根据订单状态和送达日期判断订单是否符合退货条件。"""
    svc = OrderService()
    can, msg = svc.can_return(order_id)
    if can:
        return f"✅ 订单 {order_id} 符合退货条件。{msg}"
    return f" 订单 {order_id} 不符合退货条件。{msg}"


# 退款金额阈值，超过此金额需要人工审核
REFUND_THRESHOLD = 500.0


@tool
def initiate_return(order_id: str, reason: str, refund_amount: float) -> str:
    """为订单创建退货申请，生成 RMA 编号。退款金额超过阈值时需人工审核。"""
    if refund_amount > REFUND_THRESHOLD:
        return (
            f"订单 {order_id} 的退款金额 ¥{refund_amount:.2f} 超过自动处理阈值（¥{REFUND_THRESHOLD:.2f}），"
            f"已转交人工审核，客服将在 24 小时内与您联系。"
        )
    svc = ReturnsService()
    ret = svc.create_return(order_id, reason, refund_amount)
    return (
        f"退货申请已创建！RMA：{ret.rma_number} | 订单：{order_id} | "
        f"状态：{return_status_text(ret.status)} | 退款：¥{ret.refund_amount:.2f}"
    )


# ── 工具按业务域分组 ────────────────────────────────────────
# 每个专员 Agent 只绑定自己域内的工具：工具集越小，模型选错、够不着的概率越低
ORDER_TOOLS = [
    lookup_order,            # 按订单号查详情（会顺带带出物流单号）
    lookup_orders_by_email,  # 按邮箱查名下所有订单
    search_orders,           # 按姓名/商品名模糊搜索
    track_shipment,          # 按物流单号查位置
]

RETURN_TOOLS = [
    get_return_policy,         # 退货规则
    check_return_eligibility,  # 是否还符合退货条件
    initiate_return,           # 创建退货单
]

# 专员名 → 它可用的工具；综合专员不带工具，直接回话
SPECIALIST_TOOLS = {
    "order_specialist": ORDER_TOOLS,
    "return_specialist": RETURN_TOOLS,
    "general_specialist": [],
}
