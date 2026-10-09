from domain_data import AutomationError, Element


def dismiss(session, observation=None):
    def removed_or_replaced(kind, before, after):
        return kind not in after.overlays or not session.same_view(before, after)

    for _ in range(6):
        obs = observation or session.observe("overlay")
        observation = None
        if not obs.overlays:
            return obs
        if "guess" in obs.overlays:
            # Spec line 94 (video 01:28): 放弃奖励 sits at the bottom of the
            # modal. Device evidence (2026-09-23, run 20260923-105105): the
            # modal does not scroll (3 swipes, zero movement) and the
            # handwritten glyph OCRs as 教弃奖励 (放→教) in 5/5 frames, so
            # widen the character class like the 立即* family; if the line
            # drops out entirely, tap the proven bottom-center position
            # (box (578,2751)-(851,2870)) and let the overlay-removal
            # postcondition guard the blind tap.
            matches = obs.find("[放教]弃奖励")
            if len(matches) == 1:
                target = matches[0]
            elif matches:
                target = obs.one("[放教]弃奖励")  # ambiguous: fail closed
            else:
                cx, cy = 0.496 * obs.width, 0.878 * obs.height
                target = Element("放弃奖励",
                                 (int(cx - 150), int(cy - 50),
                                  int(cx + 150), int(cy + 50)), obs.id)
            session.tap_element(
                obs,
                target,
                lambda o, before=obs: removed_or_replaced("guess", before, o),
                name="dismiss-guess",
                overlay=True,
                recover=False,
            )
        elif any(kind in obs.overlays
                 for kind in ("manor_ad", "forest_campaign", "app_update",
                              "home_promo", "farm_promo", "farm_gift",
                              "costume_promo")):
            # Homepage ads retain the manor page underneath and forest campaign
            # modals retain the forest home, so the close circle created by the
            # current observation's vision rule cannot become stale across
            # stacked overlays. The Alipay-home coupon card (2026-09-25,
            # run 41640d) joins them: Back on the home would exit the app.
            # The 版本更新 prompt (2026-10-08, run 1ed031) closes the same
            # way through its title-anchored X - and it sorts before the
            # home promo scan because the prompt itself creates the dim
            # band that scan's gate reads. The farm promo card (2026-09-26,
            # run 7d8d95) closes through its circle: Back would abandon the
            # farm whose auto-jump drawer has no static entry to return to.
            # The fertilize's 丰收礼包 popup (2026-09-30, run f427d5) too:
            # Back exited the whole 芭芭农场 container onto feed instead of
            # closing the popup. The 秋日美满 costume campaign modal
            # (2026-10-09, run e81885) closes the same way: its
            # full-screen touch layer swallowed the 家庭 nav tap while the
            # page still read manor, and Back from the manor container
            # walks the mini-program out (spec L67 closes popups with X).
            kind = next(kind for kind in ("manor_ad", "forest_campaign",
                                          "app_update", "home_promo",
                                          "farm_promo", "farm_gift",
                                          "costume_promo")
                        if kind in obs.overlays)
            close = next((e for e in obs.elements if e.text == "广告关闭"), None)
            if close is None:
                raise AutomationError(f"{kind} has no verified close control", "OVERLAY")
            session.ex.tap(
                obs,
                close,
                lambda o, before=obs, kind=kind: removed_or_replaced(kind, before, o),
                f"close-{kind.replace('_', '-')}",
                session.task,
                allow_overlay=True,
                recover=False,
            )
        elif "reward" in obs.overlays and obs.has("开心收下|我知道啦"):
            target = obs.one("开心收下|我知道啦")
            session.tap_element(
                obs,
                target,
                lambda o, before=obs: removed_or_replaced("reward", before, o),
                name="dismiss-reward",
                overlay=True,
                # Device evidence (2026-09-24, run 7798c6): the lottery's
                # prize result dims the page behind its reward overlay, so
                # every rule marker is gone, page reads UNKNOWN, and
                # validate refused this tap before dispatch even though the
                # CTA text was OCR-verified on this very observation. The
                # overlay-removal postcondition still guards the outcome -
                # same allow_unknown whitelist semantics the result-view
                # CTA tap uses in shared.lottery.
                allow_unknown=True,
                recover=False,
            )
        elif "reward" in obs.overlays and obs.has("家庭家具上新啦"):
            # Device evidence (2026-09-25, run 0c01e7): 家庭家具上新啦 is a
            # full-screen promo modal over the family page (frame mean 88 vs
            # a clean family frame's 164; every sampled band ~30 vs 130-170),
            # its card spanning y~540-2440 with the CTA 去看看 at
            # [633,2341,808,2404]. Back is NOT a closer for it: the chain
            # left the family H5 entirely (0005 -> 0007 back on manor) and
            # the blocked 签到 step then searched on the wrong page
            # (found 0). The close circle carries no OCR text and floats
            # below the card - anchor it on the card's OCR'd CTA (frame
            # 0004: CTA point (720,2372); circle center (718,2665), r~41
            # -> CTA + (-2,+293)), same bottom-center geometry as the farm
            # offer card.
            cta = obs.one("去看看")
            cx, cy = cta.point[0] - 2, cta.point[1] + 293
            target = Element("关闭家具促销卡", (cx - 90, cy - 90, cx + 90, cy + 90),
                             obs.id)
            session.tap_element(
                obs,
                target,
                lambda o, before=obs: removed_or_replaced("reward", before, o),
                name="dismiss-furniture",
                overlay=True,
                recover=False,
            )
        else:
            # Back is permitted only for a recognized dismissible reward, never a pending submission.
            if session.ex.store.unresolved(session.task) or "confirm" in obs.overlays or "overflow" in obs.overlays:
                raise AutomationError("Overlay requires task-specific handling", "OVERLAY")
            session.back_observation(
                obs,
                lambda o: not o.overlays and o.page != "UNKNOWN",
                allow_unknown=True,
                recover=False,
            )
    raise AutomationError("Overlay recovery budget exhausted", "TIMEOUT")
