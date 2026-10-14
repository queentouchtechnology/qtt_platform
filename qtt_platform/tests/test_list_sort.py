"""Sorting and paging for list APIs (qtt_platform.list_sort — pure, no bench).

	python -m unittest qtt_platform.tests.test_list_sort
"""

import unittest

from qtt_platform import list_sort

CHOICES = {"name": "customer_name asc", "newest": "creation desc"}


class ListSortTest(unittest.TestCase):
	def test_only_named_choices_reach_the_query(self):
		self.assertEqual(list_sort.order_by("newest", CHOICES, "name"), "creation desc")
		self.assertEqual(list_sort.order_by(None, CHOICES, "name"), "customer_name asc")
		self.assertEqual(list_sort.order_by("name; drop table x", CHOICES, "name"), "customer_name asc")
		self.assertEqual(list_sort.order_by("creation desc", CHOICES, "name"), "customer_name asc")  # a raw order isn't a choice

	def test_pages_are_sane(self):
		self.assertEqual(list_sort.page(None, None), (0, list_sort.PAGE))
		self.assertEqual(list_sort.page(-5, 10000), (0, 100))
		self.assertEqual(list_sort.page("40", "20"), (40, 20))
		self.assertEqual(list_sort.page("x", "y"), (0, list_sort.PAGE))


if __name__ == "__main__":
	unittest.main()
