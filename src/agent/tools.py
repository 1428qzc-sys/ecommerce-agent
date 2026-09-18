"""
Agent Tools — 用 @tool 装饰器定义 LLM 可调用的工具
类比 Java: 相当于给 LLM 暴露的接口，每个 @tool 就是一个 endpoint

关键点：
- @tool 的 docstring 会被 LLM 读取，用来决定什么时候调用这个工具
- 所以 docstring 必须清晰描述功能，包含参数说明
"""
from langchain_core.tools import tool
from src.services.order_service import OrderService
from src.services.shipping_service import ShippingService
from src.services.returns_service import ReturnsService


@tool
def lookup_order(order_id: str) -> str:
    """Look up order details by order ID. Returns customer name, status, items, and total."""
    svc = OrderService()
    order = svc.get_order(order_id)
    if not order:
        return f"Order {order_id} not found."
    items_str = ", ".join(f"{i.product_name} x{i.quantity} (${i.price:.2f})" for i in order.items)
    return (
        f"Order {order.order_id} | Customer: {order.customer_name} ({order.email}) | "
        f"Status: {order.status} | Items: {items_str} | Total: ${order.total:.2f}"
    )


@tool
def lookup_orders_by_email(email: str) -> str:
    """Look up all orders for a customer by their email address."""
    svc = OrderService()
    orders = svc.get_orders_by_email(email)
    if not orders:
        return f"No orders found for {email}."
    lines = [f"Found {len(orders)} order(s) for {email}:"]
    for o in orders:
        lines.append(f"  - {o.order_id}: {o.status}, ${o.total:.2f} ({len(o.items)} item(s))")
    return "\n".join(lines)


@tool
def search_orders(keyword: str) -> str:
    """Search orders by customer name or product name."""
    svc = OrderService()
    results = svc.search_orders(keyword)
    if not results:
        return f"No orders found matching '{keyword}'."
    lines = [f"Found {len(results)} order(s) matching '{keyword}':"]
    for o in results:
        lines.append(f"  - {o.order_id} ({o.customer_name}): {o.status}, ${o.total:.2f}")
    return "\n".join(lines)


@tool
def track_shipment(tracking_number: str) -> str:
    """Track a package by its tracking number. Returns carrier, status, and location."""
    svc = ShippingService()
    shipment = svc.track(tracking_number)
    if not shipment:
        return f"Tracking number {tracking_number} not found."
    return (
        f"Tracking: {shipment.tracking_number} | Carrier: {shipment.carrier} | "
        f"Status: {shipment.status} | Location: {shipment.location}"
    )


@tool
def get_return_policy() -> str:
    """Get the store's return policy details."""
    svc = ReturnsService()
    return svc.get_policy()


@tool
def check_return_eligibility(order_id: str) -> str:
    """Check if an order is eligible for return based on status and delivery date."""
    svc = OrderService()
    can, msg = svc.can_return(order_id)
    if can:
        return f"✅ Order {order_id} is eligible for return. {msg}"
    return f"❌ Order {order_id} is not eligible for return. {msg}"


@tool
def initiate_return(order_id: str, reason: str, refund_amount: float) -> str:
    """Initiate a return for an order. Generates an RMA number."""
    svc = ReturnsService()
    ret = svc.create_return(order_id, reason, refund_amount)
    return (
        f"Return initiated! RMA: {ret.rma_number} | Order: {order_id} | "
        f"Status: {ret.status} | Refund: ${ret.refund_amount:.2f}"
    )
