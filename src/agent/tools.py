"""
Agent Tools — LLM 可调用的工具定义
每个 @tool 的 docstring 会被 LLM 读取，用于决定何时调用该工具
"""
from langchain_core.tools import tool
from src.services.order_service import OrderService
from src.services.shipping_service import ShippingService
from src.services.returns_service import ReturnsService


@tool
def lookup_order(order_id: str) -> str:
    """根据订单号查询订单详情，返回客户姓名、状态、商品和总金额。"""
    svc = OrderService()
    order = svc.get_order(order_id)
    if not order:
        return f"订单 {order_id} 未找到。"
    items_str = ", ".join(f"{i.product_name} x{i.quantity}（¥{i.price:.2f}）" for i in order.items)
    return (
        f"订单 {order.order_id} | 客户：{order.customer_name}（{order.email}）| "
        f"状态：{order.status} | 商品：{items_str} | 总计：¥{order.total:.2f}"
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
        lines.append(f"  - {o.order_id}：{o.status}，¥{o.total:.2f}（{len(o.items)} 件商品）")
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
        lines.append(f"  - {o.order_id}（{o.customer_name}）：{o.status}，¥{o.total:.2f}")
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
        f"状态：{shipment.status} | 位置：{shipment.location}"
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


@tool
def initiate_return(order_id: str, reason: str, refund_amount: float) -> str:
    """为订单创建退货申请，生成 RMA 编号。"""
    svc = ReturnsService()
    ret = svc.create_return(order_id, reason, refund_amount)
    return (
        f"退货申请已创建！RMA：{ret.rma_number} | 订单：{order_id} | "
        f"状态：{ret.status} | 退款：¥{ret.refund_amount:.2f}"
    )
