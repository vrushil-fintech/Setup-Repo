# Diagram Examples for PR Diagram Generation
# These examples are used in the generate_pr_diagram prompt to guide the LLM

# ============================================================================
# SEQUENCE DIAGRAM EXAMPLE
# ============================================================================

SEQUENCE_EXAMPLE_TEXT = """## Example 1: Sequence Diagram (API Interactions)
Use this when PR shows API calls, method calls, or component interactions:

```json
{
  "diagram_type": "sequence",
  "nodes": [
    {"id": "user", "label": "User"},
    {"id": "frontend", "label": "Frontend"},
    {"id": "api", "label": "API Gateway"},
    {"id": "service", "label": "Backend Service"},
    {"id": "database", "label": "Database"}
  ],
  "edges": [
    {"from": "user", "to": "frontend", "label": "clicks button"},
    {"from": "frontend", "to": "api", "label": "POST /api/analyze"},
    {"from": "api", "to": "service", "label": "processes request"},
    {"from": "service", "to": "database", "label": "queries data"},
    {"from": "database", "to": "service", "label": "returns results"},
    {"from": "service", "to": "api", "label": "sends response"},
    {"from": "api", "to": "frontend", "label": "JSON response"},
    {"from": "frontend", "to": "user", "label": "displays result"}
  ]
}
```"""

# ============================================================================
# CLASS DIAGRAM EXAMPLE
# ============================================================================

CLASS_EXAMPLE_TEXT = """## Example 2: Class Diagram (Object Relationships)
Use this when PR shows class structures, inheritance, or entity relationships:

### Code Example:
```python
# Example Code: E-commerce Order System

class User:
    def __init__(self, user_id: str, name: str, email: str):
        self.user_id = user_id      # ✅ TOP-LEVEL ATTRIBUTE
        self.name = name            # ✅ TOP-LEVEL ATTRIBUTE
        self.email = email          # ✅ TOP-LEVEL ATTRIBUTE
        self.orders = []            # ✅ TOP-LEVEL ATTRIBUTE
    
    def place_order(self, order):   # ✅ TOP-LEVEL METHOD
        self.orders.append(order)
    
    def get_order_history(self):    # ✅ TOP-LEVEL METHOD
        return self.orders


class Order:
    def __init__(self, order_id: str, user: User, total_amount: float):
        self.order_id = order_id    # ✅ TOP-LEVEL ATTRIBUTE
        self.user = user            # ✅ TOP-LEVEL ATTRIBUTE
        self.total_amount = total_amount  # ✅ TOP-LEVEL ATTRIBUTE
        self.items = []             # ✅ TOP-LEVEL ATTRIBUTE
        self.payment = None         # ✅ TOP-LEVEL ATTRIBUTE
    
    def add_item(self, item):       # ✅ TOP-LEVEL METHOD
        self.items.append(item)
    
    def calculate_total(self):      # ✅ TOP-LEVEL METHOD
        return sum(item.price * item.quantity for item in self.items)
    
    def process_payment(self, payment):  # ✅ TOP-LEVEL METHOD
        self.payment = payment


class OrderItem:
    def __init__(self, product_id: str, product_name: str, price: float, quantity: int):
        self.product_id = product_id      # ✅ TOP-LEVEL ATTRIBUTE
        self.product_name = product_name  # ✅ TOP-LEVEL ATTRIBUTE
        self.price = price                # ✅ TOP-LEVEL ATTRIBUTE
        self.quantity = quantity          # ✅ TOP-LEVEL ATTRIBUTE
    
    def get_subtotal(self):         # ✅ TOP-LEVEL PUBLIC METHOD
        return self.price * self.quantity


class Payment:
    def __init__(self, payment_id: str, amount: float, method: str):
        self.payment_id = payment_id  # ✅ TOP-LEVEL ATTRIBUTE
        self.amount = amount          # ✅ TOP-LEVEL ATTRIBUTE
        self.method = method          # ✅ TOP-LEVEL ATTRIBUTE
        self.status = "pending"       # ✅ TOP-LEVEL ATTRIBUTE
    
    def process(self):              # ✅ TOP-LEVEL METHOD
        # Payment processing logic
        self.status = "completed"
    
    def refund(self):               # ✅ TOP-LEVEL METHOD
        self.status = "refunded"
```

### Corresponding JSON Spec:
```json
{
  "diagram_type": "class",
  "nodes": [
    {
      "id": "User",
      "label": "User",
      "attributes": [
        "user_id: str",
        "name: str",
        "email: str",
        "orders: List[Order]"
      ],
      "methods": [
        "place_order(order: Order)",
        "get_order_history(): List[Order]"
      ]
    },
    {
      "id": "Order",
      "label": "Order",
      "attributes": [
        "order_id: str",
        "user: User",
        "total_amount: float",
        "items: List[OrderItem]",
        "payment: Payment"
      ],
      "methods": [
        "add_item(item: OrderItem)",
        "calculate_total(): float",
        "process_payment(payment: Payment)"
      ]
    },
    {
      "id": "OrderItem",
      "label": "OrderItem",
      "attributes": [
        "product_id: str",
        "product_name: str",
        "price: float",
        "quantity: int"
      ],
      "methods": [
        "get_subtotal(): float"
      ]
    },
    {
      "id": "Payment",
      "label": "Payment",
      "attributes": [
        "payment_id: str",
        "amount: float",
        "method: str",
        "status: str"
      ],
      "methods": [
        "process()",
        "refund()"
      ]
    }
  ],
  "edges": [
    {"from": "User", "to": "Order", "label": "has many"},
    {"from": "Order", "to": "OrderItem", "label": "contains"},
    {"from": "Order", "to": "Payment", "label": "has one"}
  ]
}
```

**CRITICAL NOTES:**
- Only instance variables set in `__init__` are included as attributes
- Only public methods (no leading underscore) are included as methods
- Attribute/method names match the code EXACTLY
- Private methods like `_helper()` or `__private()` are NOT included
- Methods called inside other methods are NOT included unless they are top-level class methods"""

# ============================================================================
# FLOW DIAGRAM EXAMPLE
# ============================================================================

FLOW_EXAMPLE_TEXT = """## Example 3: Flow Diagram (Process/Workflow)
Use this ONLY when PR shows a step-by-step process or workflow:

```json
{
  "diagram_type": "flow",
  "nodes": [
    {"id": "start", "label": "Start Process"},
    {"id": "validate", "label": "Validate Input"},
    {"id": "check", "label": "Check Conditions"},
    {"id": "process", "label": "Process Data"},
    {"id": "end", "label": "Complete"}
  ],
  "edges": [
    {"from": "start", "to": "validate", "label": ""},
    {"from": "validate", "to": "check", "label": ""},
    {"from": "check", "to": "process", "label": "if valid"},
    {"from": "process", "to": "end", "label": ""}
  ]
}
```"""

# ============================================================================
# ALL DIAGRAM EXAMPLES COLLECTION
# ============================================================================

DIAGRAM_EXAMPLES = {
    "sequence": SEQUENCE_EXAMPLE_TEXT,
    "class": CLASS_EXAMPLE_TEXT,
    "flow": FLOW_EXAMPLE_TEXT
}