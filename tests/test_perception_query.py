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

    def test_two_line_row_button_pairs_despite_the_wider_gap(self):
        # Device evidence (2026-09-25, run 184a5a): the video row's CTA
        # center sits 113.5px below its title center (two description
        # lines), just past the old .035 (=112px) tolerance - row() fell
        # to the button-column fallback and blind-tapped a claim pill.
        # The row's neighbours stay >=259px away, so pairing remains unique.
        oid = "video-row"
        obs = Observation(oid, 0.0, 1440, 3200, "alipay", [
            Element("看庄园小视频", (321, 1945, 628, 1998), oid),
            Element("领取", (1179, 2059, 1282, 2111), oid),   # own, +113.5px
            Element("领取", (1179, 1687, 1282, 1738), oid),   # quiz row, -259.5px
            Element("去完成", (1158, 2387, 1301, 2443), oid),  # market row, +443.5px
        ], page="feed")

        buttons = find_elements(
            obs, ElementQuery("领取|去完成", card_title="看庄园小视频"))

        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0].bounds, (1179, 2059, 1282, 2111))

    def test_read_returns_text_without_business_decision(self):
        self.assertEqual(read_text(sample(), "庄园小课堂"), ["庄园小课堂"])


if __name__ == "__main__":
    unittest.main()
