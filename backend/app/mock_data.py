"""In-memory mock data standing in for a real orders DB / CRM / helpdesk.

Swap this module for real API calls (order service, Zendesk/Freshdesk, etc.)
when moving from POC to production — nothing else in the app needs to change
since tools.py is the only consumer.
"""
from datetime import date, timedelta

TODAY = date(2026, 9, 14)

# Canonical seed data: used directly when STORE_BACKEND=memory, and as the
# source rows loaded into Postgres by scripts/seed_postgres.py when
# STORE_BACKEND=postgres — one place to edit demo data either way.
USERS: dict[str, dict] = {
    "CUST-1": {"name": "Avery Chen", "email": "avery.chen@example.com"},
    "CUST-2": {"name": "Priya Nair", "email": "priya.nair@example.com"},
    "CUST-3": {"name": "Jordan Lee", "email": "jordan.lee@example.com"},
}

ORDERS: dict[str, dict] = {
    "ORD-1001": {
        "customer_id": "CUST-1",
        "status": "delivered",
        "items": ["Wireless Headphones", "USB-C Cable"],
        "total": 89.99,
        "order_date": str(TODAY - timedelta(days=12)),
        "delivered_date": str(TODAY - timedelta(days=8)),
        "eta": None,
        "return_window_days": 30,
    },
    "ORD-1002": {
        "customer_id": "CUST-1",
        "status": "delivered",
        "items": ["Running Shoes"],
        "total": 64.50,
        "order_date": str(TODAY - timedelta(days=15)),
        "delivered_date": str(TODAY - timedelta(days=10)),
        "eta": None,
        "return_window_days": 30,
    },
    "ORD-1003": {
        "customer_id": "CUST-2",
        "status": "shipped",
        "items": ["Espresso Machine"],
        "total": 249.00,
        "order_date": str(TODAY - timedelta(days=3)),
        "delivered_date": None,
        "eta": str(TODAY + timedelta(days=2)),
        "return_window_days": 30,
    },
    "ORD-1004": {
        "customer_id": "CUST-3",
        "status": "delayed",
        "items": ["Desk Lamp", "Notebook Set"],
        "total": 42.30,
        "order_date": str(TODAY - timedelta(days=9)),
        "delivered_date": None,
        "eta": str(TODAY + timedelta(days=5)),
        "return_window_days": 30,
    },
    "ORD-1005": {
        "customer_id": "CUST-2",
        "status": "delivered",
        "items": ["Bluetooth Speaker"],
        "total": 39.99,
        "order_date": str(TODAY - timedelta(days=55)),
        "delivered_date": str(TODAY - timedelta(days=50)),
        "eta": None,
        "return_window_days": 30,
    },
}

FAQS: list[dict] = [
    {
        "question": "What are your standard shipping times?",
        "answer": "Standard shipping takes 3-5 business days. Express shipping (available at checkout) takes 1-2 business days.",
        "tags": ["shipping", "delivery", "eta"],
    },
    {
        "question": "Do you ship internationally?",
        "answer": "Yes, we ship to over 30 countries. International orders typically take 7-14 business days and may be subject to customs fees.",
        "tags": ["shipping", "international", "customs"],
    },
    {
        "question": "What payment methods do you accept?",
        "answer": "We accept Visa, Mastercard, American Express, PayPal, and Apple Pay.",
        "tags": ["payment", "billing", "checkout"],
    },
    {
        "question": "How do I track my order?",
        "answer": "Once your order ships, you'll receive a tracking link by email. You can also ask this assistant for your order status any time.",
        "tags": ["tracking", "shipping", "order status"],
    },
    {
        "question": "Can I change my shipping address after ordering?",
        "answer": "You can change your shipping address within 1 hour of placing the order by contacting support. After that, the order may already be processing.",
        "tags": ["address", "change order", "shipping"],
    },
    {
        "question": "What is your return policy?",
        "answer": "Items can be returned within 30 days of delivery for a full refund, provided they're unused and in original packaging.",
        "tags": ["return", "refund", "policy"],
    },
    {
        "question": "Do you offer warranties on electronics?",
        "answer": "All electronics come with a 1-year manufacturer warranty covering defects. Accidental damage isn't covered.",
        "tags": ["warranty", "electronics", "defect"],
    },
    {
        "question": "What are your customer support hours?",
        "answer": "Our support team is available Monday-Friday, 9am-7pm ET. This AI assistant is available 24/7 for common questions.",
        "tags": ["support hours", "contact", "human agent"],
    },
]

# Populated at runtime by tools.create_support_ticket
TICKETS: dict[str, dict] = {}
