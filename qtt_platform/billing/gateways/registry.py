import frappe

from qtt_platform.billing.gateways.base import PaymentGateway
from qtt_platform.billing.gateways.razorpay_gateway import RazorpayGateway

_GATEWAY_CLASSES = {
	"razorpay": RazorpayGateway,
}


def get_gateway(gateway_key: str) -> PaymentGateway:
	gateway_cls = _GATEWAY_CLASSES.get(gateway_key)
	if not gateway_cls:
		frappe.throw(f"Unknown payment gateway: {gateway_key}")
	return gateway_cls()
