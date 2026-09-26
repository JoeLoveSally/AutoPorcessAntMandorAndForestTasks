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
        # Device evidence (2026-09-24, run bc2b84): the row carries a bare
        # lower-left game logo 抽抽乐 beside its bracketed title
        # 【抽抽乐】丹桂秋光来啦, and the old ^(?!.*IP).*抽抽乐 (no closing
        # anchor) matched both, failing closed with Ambiguous task
        # identity. The closing 】 is the one text the logo never carries;
        # \s* tolerates the observed 【抽抽乐 】 OCR spacing variant. Run
        # ffc3ae then showed the IP side carries NO brackets in its active
        # period - the row reads IP抽抽乐江苏文旅装扮 and its left tag is
        # 限定IP rather than a bare IP抽抽乐 twin - so only the ^IP prefix
        # anchors it, which still excludes the plain 抽抽乐 title.
        ("manor.feed.lottery", "manor_feed",
         partial(manor.lottery, r"^【?抽抽乐\s*】")),
        ("manor.feed.ip_lottery", "manor_feed",
         partial(manor.lottery, r"^【?IP抽抽乐")),
        ("manor.feed.farm", "manor_feed", manor.farm),
        # Device evidence (2026-09-25, run 8f3a63): the promo period renames
        # the row title to 家庭×阿福新活动上线 (OCR swings the collab
        # separator ×/入/X between captures) while its description still
        # ends 去家庭还可获得90g饲料哦 - the old bare 去家庭逛一逛 matched
        # nothing and the row scan died as Required task missing after a
        # full scroll. Keep the original title for post-promo periods; the
        # {0,2} gap covers the observed separator swings, and neither alt
        # can match the description.
        ("manor.feed.family", "manor_feed",
         partial(manor.browse, "去家庭逛一逛|家庭.{0,2}阿福新活动上线", instant=True)),
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
