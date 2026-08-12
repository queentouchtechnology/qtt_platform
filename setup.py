from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

# get version from __version__ variable in qtt_platform/__init__.py
from qtt_platform import __version__ as version

setup(
    name="qtt_platform",
    version=version,
    description="QTT SaaS Platform — reusable multi-tenant, multi-product infrastructure (Tenant, Membership, Product Access, Subscriptions, Entitlements, Usage, AI, Billing, Audit) for Quiz Master Plus and future QTT products.",
    author="Queen Touch Technology",
    author_email="queentouchtech@gmail.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
