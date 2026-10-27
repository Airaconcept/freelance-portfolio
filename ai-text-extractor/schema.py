"""The fields to extract. Edit this file to change what ends up in Excel.

The same definitions are used to (1) write the LLM prompt, (2) validate/convert the answer,
(3) build the Excel columns - so a new field only has to be added here.
"""

DOC_TYPES = {
    "invoice": {
        "description": "a bill or invoice from a supplier",
        "fields": {
            "vendor": ("string", "company that issued the invoice"),
            "customer": ("string", "company the invoice is addressed to"),
            "invoice_number": ("string", "invoice / bill number exactly as written"),
            "invoice_date": ("date", "issue date, YYYY-MM-DD"),
            "due_date": ("date", "payment due date, YYYY-MM-DD, null if not stated"),
            "currency": ("string", "ISO 4217 code, e.g. USD, EUR, GBP"),
            "subtotal": ("number", "amount before tax"),
            "tax": ("number", "tax / VAT amount"),
            "total": ("number", "total amount payable"),
        },
        "line_items": {
            "description": ("string", "item description"),
            "quantity": ("number", "quantity"),
            "unit_price": ("number", "price per unit"),
            "amount": ("number", "line total"),
        },
    },
    "email": {
        "description": "a customer e-mail or message",
        "fields": {
            "sender_name": ("string", "name of the person who wrote it"),
            "company": ("string", "sender's company"),
            "subject": ("string", "subject line"),
            "intent": ("enum:order|quote_request|complaint|question|other", "what the sender wants"),
            "items_mentioned": ("string", "products and quantities mentioned, comma-separated"),
            "reference": ("string", "order / invoice number mentioned, null if none"),
            "deadline": ("date", "date by which the sender needs something, YYYY-MM-DD, null if none"),
            "urgency": ("enum:high|normal|low", "high = urgent or a problem, low = explicitly no rush"),
            "summary": ("string", "one sentence summary"),
        },
    },
}
