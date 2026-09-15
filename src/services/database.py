"""
Database — SQLite 数据库初始化 + 种子数据
类比 Java: 相当于 Spring Boot 的 schema.sql + data.sql
"""
import os
from sqlalchemy import create_engine, Column, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timedelta

Base = declarative_base()


# ── 数据模型 ──────────────────────────────────────────────────
class Customer(Base):
    __tablename__ = "customers"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String)
    orders = relationship("Order", back_populates="customer")


class Order(Base):
    __tablename__ = "orders"
    order_id = Column(String, primary_key=True)
    customer_id = Column(String, ForeignKey("customers.id"))
    status = Column(String, nullable=False)  # pending / shipped / delivered / cancelled
    total = Column(Float, nullable=False)
    order_date = Column(DateTime, default=datetime.utcnow)
    delivery_date = Column(DateTime, nullable=True)
    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(String, primary_key=True)
    order_id = Column(String, ForeignKey("orders.order_id"))
    product_name = Column(String, nullable=False)
    quantity = Column(String, nullable=False)  # 用字符串，如 "1", "2 pairs"
    price = Column(Float, nullable=False)
    order = relationship("Order", back_populates="items")


class Shipment(Base):
    __tablename__ = "shipments"
    tracking_number = Column(String, primary_key=True)
    order_id = Column(String, ForeignKey("orders.order_id"))
    carrier = Column(String, nullable=False)   # FedEx / UPS / USPS
    status = Column(String, nullable=False)    # in_transit / delivered / returned
    estimated_delivery = Column(DateTime, nullable=True)
    location = Column(String, default="")


# ── 数据库引擎 ──────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "ecommerce.db")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)


def get_session():
    return SessionLocal()


def init_db():
    """建表 + 填充种子数据（幂等：先删后建）"""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    _seed()


def _seed():
    """填充演示数据 — 12 个订单，覆盖各种状态"""
    session = get_session()
    now = datetime.utcnow()

    # 客户
    customers = [
        Customer(id="C001", name="James Wilson", email="james@example.com", phone="555-0101"),
        Customer(id="C002", name="Sarah Chen", email="sarah@example.com", phone="555-0102"),
        Customer(id="C003", name="Mike Johnson", email="mike@example.com", phone="555-0103"),
        Customer(id="C004", name="Emily Davis", email="emily@example.com", phone="555-0104"),
    ]
    session.add_all(customers)

    # 订单（各种状态：delivered / shipped / pending / cancelled / returned）
    orders = [
        Order(order_id="ORD-1001", customer_id="C001", status="delivered", total=105.97,
              order_date=now - timedelta(days=10), delivery_date=now - timedelta(days=5)),
        Order(order_id="ORD-1002", customer_id="C001", status="shipped", total=249.99,
              order_date=now - timedelta(days=3), delivery_date=None),
        Order(order_id="ORD-1003", customer_id="C002", status="pending", total=59.99,
              order_date=now - timedelta(days=1)),
        Order(order_id="ORD-1004", customer_id="C002", status="cancelled", total=89.50,
              order_date=now - timedelta(days=7)),
        Order(order_id="ORD-1005", customer_id="C003", status="delivered", total=329.00,
              order_date=now - timedelta(days=20), delivery_date=now - timedelta(days=15)),
        Order(order_id="ORD-1006", customer_id="C003", status="delivered", total=45.00,
              order_date=now - timedelta(days=25), delivery_date=now - timedelta(days=20)),
        Order(order_id="ORD-1007", customer_id="C004", status="shipped", total=175.50,
              order_date=now - timedelta(days=2)),
        Order(order_id="ORD-1008", customer_id="C004", status="delivered", total=62.00,
              order_date=now - timedelta(days=30), delivery_date=now - timedelta(days=25)),
        Order(order_id="ORD-1009", customer_id="C001", status="delivered", total=199.99,
              order_date=now - timedelta(days=8), delivery_date=now - timedelta(days=3)),
        Order(order_id="ORD-1010", customer_id="C002", status="pending", total=310.00,
              order_date=now - timedelta(days=1)),
        Order(order_id="ORD-1011", customer_id="C003", status="shipped", total=88.75,
              order_date=now - timedelta(days=4)),
        Order(order_id="ORD-1012", customer_id="C004", status="delivered", total=420.00,
              order_date=now - timedelta(days=12), delivery_date=now - timedelta(days=7)),
    ]
    session.add_all(orders)

    # 订单商品
    items = [
        OrderItem(id="I001", order_id="ORD-1001", product_name="Wireless Headphones", quantity="1", price=105.97),
        OrderItem(id="I002", order_id="ORD-1001", product_name="USB-C Cable", quantity="2", price=0.00),
        OrderItem(id="I003", order_id="ORD-1002", product_name="Smart Watch", quantity="1", price=249.99),
        OrderItem(id="I004", order_id="ORD-1003", product_name="Phone Case", quantity="1", price=29.99),
        OrderItem(id="I005", order_id="ORD-1003", product_name="Screen Protector", quantity="2", price=15.00),
        OrderItem(id="I006", order_id="ORD-1004", product_name="Bluetooth Speaker", quantity="1", price=89.50),
        OrderItem(id="I007", order_id="ORD-1005", product_name="Laptop Stand", quantity="1", price=79.00),
        OrderItem(id="I008", order_id="ORD-1005", product_name="Mechanical Keyboard", quantity="1", price=250.00),
        OrderItem(id="I009", order_id="ORD-1006", product_name="Mouse Pad", quantity="1", price=45.00),
        OrderItem(id="I010", order_id="ORD-1007", product_name="Webcam HD", quantity="1", price=175.50),
        OrderItem(id="I011", order_id="ORD-1008", product_name="HDMI Cable", quantity="2", price=31.00),
        OrderItem(id="I012", order_id="ORD-1009", product_name="Noise Cancelling Earbuds", quantity="1", price=199.99),
        OrderItem(id="I013", order_id="ORD-1010", product_name="Tablet", quantity="1", price=310.00),
        OrderItem(id="I014", order_id="ORD-1011", product_name="USB Hub", quantity="1", price=88.75),
        OrderItem(id="I015", order_id="ORD-1012", product_name="Monitor 27 inch", quantity="1", price=420.00),
    ]
    session.add_all(items)

    # 物流信息
    shipments = [
        Shipment(tracking_number="FDX-78901234", order_id="ORD-1001", carrier="FedEx",
                 status="delivered", location="Delivered at front door"),
        Shipment(tracking_number="UPS-45678901", order_id="ORD-1002", carrier="UPS",
                 status="in_transit", estimated_delivery=now + timedelta(days=2),
                 location="In transit - Regional sorting facility"),
        Shipment(tracking_number="USPS-11223344", order_id="ORD-1005", carrier="USPS",
                 status="delivered", location="Delivered to mailbox"),
        Shipment(tracking_number="FDX-55667788", order_id="ORD-1007", carrier="FedEx",
                 status="in_transit", estimated_delivery=now + timedelta(days=3),
                 location="In transit - Out for delivery"),
        Shipment(tracking_number="UPS-99887766", order_id="ORD-1009", carrier="UPS",
                 status="delivered", location="Delivered to reception"),
        Shipment(tracking_number="FDX-33445566", order_id="ORD-1011", carrier="FedEx",
                 status="in_transit", estimated_delivery=now + timedelta(days=1),
                 location="In transit - Local facility"),
    ]
    session.add_all(shipments)

    session.commit()
    session.close()


# 启动时自动初始化
if __name__ == "__main__":
    init_db()
    print("Database initialized with seed data.")
