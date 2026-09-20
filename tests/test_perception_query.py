import unittest

from domain_data import AutomationError, Element, Observation
from screen_perception.query import ElementQuery, find_elements, find_one, read_text


def sample():
    oid = "obs-1"
    elements = [
        Element("庄园小课堂", (100, 400, 400, 460), oid),
        Element("去答题", (1100, 400, 1300, 460), oid),
        Element("看庄园小视频", (100, 800, 450, 860), oid),
        Element("去完成", (1100, 800, 1300, 860), oid),
        Element("去答题", (1100, 1500, 1300, 1560), oid),
    ]
    return Observation(oid, 0.0, 1440, 3200, "alipay", elements, page="feed")


class QueryTests(unittest.TestCase):
    def test_card_title_scopes_element(self):
        obs = sample()
        target = find_one(obs, ElementQuery("去答题", card_title="庄园小课堂"))
        self.assertEqual(target.point, (1200, 430))
        self.assertEqual(target.observation, obs.id)

    def test_global_query_rejects_two_identical_buttons(self):
        with self.assertRaises(AutomationError) as raised:
            find_one(sample(), ElementQuery("去答题"))
        self.assertEqual(raised.exception.code, "AMBIGUOUS")

    def test_missing_title_never_falls_back_to_global_button(self):
        with self.assertRaises(AutomationError):
            find_one(sample(), ElementQuery("去答题", card_title="不存在的任务"))

    def test_card_title_ambiguity_is_not_silently_resolved(self):
        obs = sample()
        obs.elements.append(Element("庄园小课堂", (100, 1200, 400, 1260), obs.id))
        with self.assertRaises(AutomationError):
            find_elements(obs, ElementQuery("去答题", card_title="庄园小课堂"))

    def test_read_returns_text_without_business_decision(self):
        self.assertEqual(read_text(sample(), "庄园小课堂"), ["庄园小课堂"])


if __name__ == "__main__":
    unittest.main()
