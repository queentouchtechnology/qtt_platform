"""
Bench-independent tests for the website knowledge (qtt_platform.assistant.site_knowledge — pure).

	python -m unittest qtt_platform.tests.test_site_knowledge -v
"""

import unittest

from qtt_platform.assistant import site_knowledge as s

SITE = s.SITE
PAGES = [
	{"url": f"{SITE}/packages/software-testing-qa/", "title": "Software Testing & QA", "description": "Website, mobile app and API testing",
	 "text": "Testing is led by QTT's QA lead. Mobile app QA on real devices. Regression testing."},
	{"url": f"{SITE}/packages/restaurant-food-ordering/", "title": "Restaurant & Bakery Website and Online Ordering Package", "description": "",
	 "text": "Online ordering for restaurants and bakeries. Menu, WhatsApp orders."},
	{"url": f"{SITE}/case-studies/ganesh-bakery-thoothukudi/", "title": "Ganesh Bakery, Thoothukudi", "description": "",
	 "text": "A bakery website with online orders."},
	{"url": f"{SITE}/insights/website-and-app-services/pre-launch-qa-checklist-website-app/", "title": "Pre-launch QA checklist", "description": "",
	 "text": "Testing checklist before you launch your website or app."},
	{"url": f"{SITE}/locations/madurai/", "title": "IT company in Madurai", "description": "", "text": "We serve Madurai businesses."},
	{"url": f"{SITE}/privacy-policy.html", "title": "Privacy Policy", "description": "", "text": "Privacy."},
]


class ExtractTests(unittest.TestCase):
	def test_page_text_without_menus_scripts_or_footer(self):
		html = """<html><head><title>Software Testing &amp; QA | QTT</title><meta name="description" content="QA by an expert">
		<script>var x=1</script></head><body><nav><a>Home</a><a>Services</a></nav>
		<h1>Software Testing</h1><p>Find the bugs   before your customers do.</p><ul><li>Website QA</li><li>API testing</li></ul>
		<footer>© QTT · Contact</footer></body></html>"""
		p = s.page_from_html(f"{SITE}/packages/software-testing-qa/", html)
		self.assertEqual(p["title"], "Software Testing & QA")
		self.assertEqual(p["description"], "QA by an expert")
		self.assertEqual(p["text"], "# Software Testing\nFind the bugs before your customers do.\n- Website QA\n- API testing")


class MapTests(unittest.TestCase):
	def test_every_page_by_section_without_legal_pages(self):
		index = s.site_index(PAGES)
		self.assertTrue(index.startswith("Packages (ready bundles): Restaurant & Bakery Website and Online Ordering Package; Software Testing & QA"))
		self.assertIn("Case studies: Ganesh Bakery, Thoothukudi", index)
		self.assertIn("Locations we serve: IT company in Madurai", index)
		self.assertNotIn("Privacy", index)


class PickTests(unittest.TestCase):
	def urls(self, q):
		return [p["url"].replace(SITE, "") for p in s.pick_pages(PAGES, q)]

	def test_the_matching_offer_comes_first(self):
		self.assertEqual(self.urls("do you test mobile apps?")[0], "/packages/software-testing-qa/")  # test ↔ testing
		self.assertEqual(self.urls("website for my bakery")[:2],
						 ["/packages/restaurant-food-ordering/", "/case-studies/ganesh-bakery-thoothukudi/"])
		self.assertEqual(self.urls("office in madurai?"), ["/locations/madurai/"])

	def test_articles_rank_below_offers(self):
		urls = self.urls("testing checklist")
		self.assertLess(urls.index("/packages/software-testing-qa/"), urls.index("/insights/website-and-app-services/pre-launch-qa-checklist-website-app/"))

	def test_a_greeting_needs_no_pages(self):
		self.assertEqual(s.pick_pages(PAGES, "Hai"), [])
		self.assertEqual(s.pick_pages(PAGES, "hello sir, thanks"), [])

	def test_the_size_budget_is_kept(self):
		self.assertLessEqual(len(s.pick_pages(PAGES, "bakery website testing", budget=120)), 2)


if __name__ == "__main__":
	unittest.main()
