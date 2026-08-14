from pathlib import Path

from ants_automation.perception.ui_tree import UiTree


FIXTURES = Path(__file__).parent / "fixtures"


def test_tree_finds_home_entry():
    tree = UiTree.from_file(FIXTURES / "alipay_home.xml")
    node = tree.find_exact(("蚂蚁庄园",), clickable_only=True)
    assert node is not None
    assert node.bounds.center == (150, 100)


def test_tree_keeps_visible_labels():
    tree = UiTree.from_file(FIXTURES / "manor_family.xml")
    assert tree.visible_labels() == ("欢乐全家桶", "立即签到")
