"""
Order Service — 订单查询与退货判断
"""
from datetime import datetime, timedelta
from src.services.database import get_session, Order, OrderItem, Customer


class OrderItemInfo:
    def __init__(self, product_name, quantity, price):
        self.product_name = product_name
        self.quantity = quantity
        self.price = price


class OrderDetail:
    def __init__(self, order_id, customer_name, email, status, total, order_date, delivery_date, items):
        self.order_id = order_id
        self.customer_name = customer_name
        self.email = email
        self.status = status
        self.total = total
        self.order_date = order_date
        self.delivery_date = delivery_date
        self.items = items  # list[OrderItemInfo]


class OrderService:
    def get_order(self, order_id: str) -> OrderDetail | None:
        """根据订单号查询订单详情"""
        session = get_session()
        order = session.query(Order).filter(Order.order_id == order_id).first()
        if not order:
            session.close()
            return None
        detail = OrderDetail(
            order_id=order.order_id,
            customer_name=order.customer.name,
            email=order.customer.email,
            status=order.status,
            total=order.total,
            order_date=order.order_date,
            delivery_date=order.delivery_date,
            items=[OrderItemInfo(i.product_name, i.quantity, i.price) for i in order.items],
        )
        session.close()
        return detail

    def get_orders_by_email(self, email: str) -> list[OrderDetail]:
        """根据邮箱查询该客户的所有订单"""
        session = get_session()
        customer = session.query(Customer).filter(Customer.email == email).first()
        if not customer:
            session.close()
            return []
        orders = [self._to_detail(o) for o in customer.orders]
        session.close()
        return orders

    def search_orders(self, keyword: str) -> list[OrderDetail]:
        """模糊搜索：按客户名或商品名匹配"""
        session = get_session()
        results = []
        # 按客户名搜
        customers = session.query(Customer).filter(Customer.name.ilike(f"%{keyword}%")).all()
        for c in customers:
            for o in c.orders:
                results.append(self._to_detail(o))
        # 按商品名搜
        items = session.query(OrderItem).filter(OrderItem.product_name.ilike(f"%{keyword}%")).all()
        for item in items:
            detail = self._to_detail(item.order)
            if detail not in results:
                results.append(detail)
        session.close()
        return results

    def can_return(self, order_id: str) -> tuple[bool, str]:
        """判断订单是否可退货：已送达 + 14天内"""
        order = self.get_order(order_id)
        if not order:
            return False, "订单未找到"
        if order.status == "cancelled":
            return False, "订单已取消，无法退货"
        if order.status != "delivered":
            return False, "订单尚未送达，暂不能退货"
        if order.delivery_date:
            days_since = (datetime.utcnow() - order.delivery_date).days
            if days_since > 14:
                return False, f"退货期限（14天）已过期，订单于 {days_since} 天前送达"
        return True, "符合14天内退货条件"

    def get_all_orders(self) -> list[OrderDetail]:
        session = get_session()
        orders = session.query(Order).all()
        result = [self._to_detail(o) for o in orders]
        session.close()
        return result

    def _to_detail(self, order: Order) -> OrderDetail:
        return OrderDetail(
            order_id=order.order_id,
            customer_name=order.customer.name,
            email=order.customer.email,
            status=order.status,
            total=order.total,
            order_date=order.order_date,
            delivery_date=order.delivery_date,
            items=[OrderItemInfo(i.product_name, i.quantity, i.price) for i in order.items],
        )
