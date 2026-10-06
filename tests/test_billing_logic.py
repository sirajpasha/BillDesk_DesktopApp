from app.services.billing_service import BillingService

def test_invoice_number_format(fake_db):
    service = BillingService(fake_db)
    assert service.next_invoice_number().count('-') == 1
