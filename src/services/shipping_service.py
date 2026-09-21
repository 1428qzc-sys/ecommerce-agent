"""
Shipping Service — 物流追踪
"""
from src.services.database import get_session, Shipment


class ShipmentInfo:
    def __init__(self, tracking_number, order_id, carrier, status, estimated_delivery, location):
        self.tracking_number = tracking_number
        self.order_id = order_id
        self.carrier = carrier
        self.status = status
        self.estimated_delivery = estimated_delivery
        self.location = location


class ShippingService:
    def track(self, tracking_number: str) -> ShipmentInfo | None:
        """根据物流单号查询物流状态"""
        session = get_session()
        s = session.query(Shipment).filter(Shipment.tracking_number == tracking_number).first()
        if not s:
            session.close()
            return None
        info = ShipmentInfo(
            tracking_number=s.tracking_number,
            order_id=s.order_id,
            carrier=s.carrier,
            status=s.status,
            estimated_delivery=s.estimated_delivery,
            location=s.location,
        )
        session.close()
        return info

    def get_readable_status(self, tracking_number: str) -> str:
        """获取可读的物流状态描述"""
        shipment = self.track(tracking_number)
        if not shipment:
            return "未找到该物流单号"
        status_map = {
            "in_transit": f"运输中，承运商：{shipment.carrier}。{shipment.location}",
            "delivered": f"已签收，承运商：{shipment.carrier}。{shipment.location}",
            "returned": f"已退回，承运商：{shipment.carrier}。",
        }
        result = status_map.get(shipment.status, f"状态：{shipment.status}")
        if shipment.estimated_delivery and shipment.status == "in_transit":
            result += f" 预计送达：{shipment.estimated_delivery.strftime('%Y-%m-%d')}"
        return result
