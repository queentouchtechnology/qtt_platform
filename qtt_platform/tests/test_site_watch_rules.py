import unittest

from qtt_platform import site_watch_rules as r


class TestParse(unittest.TestCase):
	def test_label_and_plain_lines(self):
		sites = r.parse_sites("QuizMaster | https://app.quizmasterplus.in/api/method/ping\n\n# off\nhttps://queentouchtech.in")
		self.assertEqual(sites, [{"label": "QuizMaster", "url": "https://app.quizmasterplus.in/api/method/ping"},
								 {"label": "queentouchtech.in", "url": "https://queentouchtech.in"}])

	def test_skips_bad_and_duplicate(self):
		self.assertEqual(r.parse_sites("not a url\nhttps://a.in\nA | https://a.in"), [{"label": "a.in", "url": "https://a.in"}])
		self.assertEqual(r.parse_sites(None), [])


class TestStep(unittest.TestCase):
	def test_one_failure_is_not_down(self):
		state, alert = r.step(None, ok=False, problem="HTTP 502", label="QuizMaster")
		self.assertEqual((state["fails"], state["down"], alert), (1, False, None))

	def test_second_failure_alerts_once(self):
		state, alert = r.step({"fails": 1, "down": False}, ok=False, problem="HTTP 502", label="QuizMaster")
		self.assertTrue(state["down"])
		self.assertEqual(alert, "QuizMaster is down — HTTP 502.")
		state, alert = r.step(state, ok=False, problem="HTTP 502", label="QuizMaster")
		self.assertIsNone(alert)

	def test_back_up_alerts(self):
		state, alert = r.step({"fails": 5, "down": True}, ok=True, problem=None, label="QuizMaster")
		self.assertEqual((state, alert), ({"fails": 0, "down": False, "problem": None}, "QuizMaster is back up."))

	def test_up_and_staying_up_is_quiet(self):
		self.assertIsNone(r.step({"fails": 0, "down": False}, ok=True, problem=None, label="x")[1])


class TestDescribe(unittest.TestCase):
	def test_only_200_is_up(self):
		self.assertEqual(r.describe(200, None), (True, None))
		self.assertEqual(r.describe(404, None), (False, "HTTP 404"))
		self.assertEqual(r.describe(None, "timed out"), (False, "timed out"))


class TestDownSites(unittest.TestCase):
	def test_shaped_like_a_server(self):
		sites = [{"label": "QuizMaster", "url": "u1"}, {"label": "Other", "url": "u2"}]
		out = r.down_sites(sites, {"u1": {"down": True, "problem": "HTTP 404"}, "u2": {"down": False}})
		self.assertEqual(out, [{"key": None, "title": "QuizMaster", "status": "offline", "problems": "HTTP 404"}])


if __name__ == "__main__":
	unittest.main()
