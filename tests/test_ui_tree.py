from screen_perception import UiTree

XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node text="" content-desc="" resource-id="card" class="View" clickable="true" enabled="true" bounds="[100,400][1300,650]">
    <node text="庄园小课堂" content-desc="" resource-id="" class="TextView" clickable="false" enabled="true" bounds="[150,450][700,550]" />
    <node text="去答题" content-desc="" resource-id="" class="Button" clickable="true" enabled="true" bounds="[1050,460][1250,560]" />
  </node>
</hierarchy>""".encode()


def test_finds_clickable_parent():
    tree = UiTree.from_bytes(XML)
    element = tree.element("obs", "quiz", "庄园小课堂")
    assert element is not None
    assert element.bounds.center == (700, 525)
    assert element.source == "ui_tree"


def test_finds_task_action_in_same_row():
    tree = UiTree.from_bytes(XML)
    element = tree.task_action("obs", "quiz", ("庄园小课堂",), ("去答题",))
    assert element is not None
    assert element.bounds.center == (1150, 510)
    assert element.source == "ui_tree:task_action"


def test_visible_webview_copy_wins_over_hidden_prerendered_copy():
    tree = UiTree.from_bytes(
        b"""<?xml version='1.0'?><hierarchy rotation='0'>
        <node text='confirm' content-desc='' resource-id='' class='View' clickable='true' enabled='true' bounds='[0,0][0,0]' />
        <node text='confirm' content-desc='' resource-id='' class='View' clickable='true' enabled='true' bounds='[100,200][300,400]' />
        </hierarchy>"""
    )
    element = tree.element("obs", "confirm", "confirm")
    assert element is not None
    assert element.bounds.center == (200, 300)


def test_hidden_only_node_is_not_an_action():
    tree = UiTree.from_bytes(
        b"""<?xml version='1.0'?><hierarchy rotation='0'>
        <node text='confirm' content-desc='' resource-id='' class='View' clickable='true' enabled='true' bounds='[0,0][0,0]' />
        </hierarchy>"""
    )
    assert tree.element("obs", "confirm", "confirm") is None
