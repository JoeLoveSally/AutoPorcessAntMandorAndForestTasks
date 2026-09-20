from functools import partial

from workflow.forest.daily import Forest
from workflow.manor.daily import Manor
from workflow.manor.home import ManorHome


def build_tasks(session):
    home, manor, forest = ManorHome(session), Manor(session), Forest(session)
    tasks = [
        ("manor.home.reward_friends", "manor_home", home.reward_friends),
        ("manor.home.bring_home", "manor_home", home.bring_home),
        ("manor.home.diary", "manor_home", home.diary),
        ("manor.family.donate_egg", "manor_family", manor.family_donate),
        ("manor.family.meal", "manor_family", partial(manor.family_action, "meal")),
        ("manor.family.feed", "manor_family", partial(manor.family_action, "feed")),
        ("manor.feed.sign", "manor_feed", manor.sign),
        ("manor.feed.quiz", "manor_feed", manor.quiz),
        ("manor.feed.video", "manor_feed", partial(manor.browse, "看庄园小视频")),
        ("manor.feed.market", "manor_feed", partial(manor.browse, "去杂货铺逛一逛", swipe=True)),
        ("manor.feed.lottery", "manor_feed", partial(manor.lottery, r"^(?!.*IP).*抽抽乐")),
        ("manor.feed.ip_lottery", "manor_feed", partial(manor.lottery, "IP抽抽乐")),
        ("manor.feed.farm", "manor_feed", manor.farm),
        ("manor.feed.family", "manor_feed", partial(manor.browse, "去家庭逛一逛", instant=True)),
        ("manor.feed.kitchen", "manor_feed", manor.kitchen),
    ]
    for name, title, claim in (("forest", "去蚂蚁森林逛一逛", False),
                               ("sesame", "去芝麻攒粒攻略逛一逛", True),
                               ("village", "去蚂蚁新村逛一逛", True),
                               ("member", "去支付宝会员签到", True)):
        tasks.append(("manor.feed."+name, "manor_feed",
                      partial(manor.browse, title, instant=True, optional=True, claim=claim)))
    tasks.extend([
        ("forest.self", "forest", forest.collect_self),
        ("forest.friends", "forest", forest.friends),
        ("forest.love", "forest", partial(forest.water, True)),
        ("forest.cooperate", "forest", partial(forest.water, False)),
        ("forest.rain", "forest", forest.rain),
    ])
    return tasks
