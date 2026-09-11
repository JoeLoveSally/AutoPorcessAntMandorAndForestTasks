from __future__ import annotations

import json
import re
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict

import cv2
import numpy as np

from domain_data import AutomationError, Element, Observation

# More specific child pages precede parent pages whose title remains visible.
PAGE_RULES = (
    ("donate_success", ("捐蛋成功",)),
    ("donate_quantity", ("选择捐蛋数量", "立即捐蛋")),
    ("donate_detail", ("立即捐蛋",)),
    ("donate_projects", ("去捐蛋", "爱心|助力|项目")),
    ("family_tasks", ("攒亲密度", "请家人|每日捐蛋|帮家人")),
    ("family", ("家庭", "立即签到|攒亲密度")),
    ("diary", ("小鸡日记", "贴贴小鸡|明日再来")),
    ("quiz", ("庄园小课堂",)),
    ("feed", ("饲料任务",)),
    ("kitchen", ("小鸡厨房", "做美食|食材")),
    ("ingredient_shop", ("献爱心", "食材")),
    ("farm_tasks", ("做任务集肥料",)),
    ("farm", ("芭芭农场", "施肥|肥料")),
    ("lottery", ("立即抽奖", "每日签到|抽奖机会|去逛逛|杂货铺")),
    ("treasure", ("森林寻宝",)),
    ("rain", ("能量雨", "立即开始|送TA机会|再来一次|今日已|获得|明日")),
    ("love", ("真爱合种", "为爱攒能量|攒能量|今日")),
    ("cooperate", ("合种", "浇水")),
    ("forest_friend", ("的蚂蚁森林", "一键收|找能量|找更多能量|收取TA")),
    ("forest", ("蚂蚁森林", "森林广场|找能量|合种")),
    ("manor_friend", ("的蚂蚁庄园", "蹭吃|雇佣|带小鸡")),
    ("manor", ("蚂蚁庄园", "领饲料", "家庭")),
    ("ad", ("可领饲料|可领奖励|浏览完成|任务.*浏览|浏览.*秒|滑动.*秒",)),
    ("alipay", ("扫一扫", "收付款|收钱", "我的")),
)


def classify(observation):
    for name, patterns in PAGE_RULES:
        if all(observation.has(p) for p in patterns):
            observation.page = name
            break
    for name, pattern in (("guess", "猜价格|猜价"), ("overflow", "超过.*上限|超出.*上限|饲料袋已满"),
                          ("reward", "获得奖励|开心收下"), ("confirm", "确认喂食|选择美食|兑换确认")):
        if observation.has(pattern):
            observation.overlays.append(name)
    # The manor homepage may keep the underlying card text visible while a
    # modal ad dims the whole screen. Treat the ad as an overlay only when a
    # dimmed modal region and its dismiss control are both present; the same
    # words on the normal homepage remain ordinary page content.
    if observation.page == "manor" and observation.image is not None:
        image = observation.image
        h, w = image.shape[:2]
        center = image[int(h * .25):int(h * .86), int(w * .08):int(w * .92)]
        if float(center.mean()) < 125 and observation.has("立即领现金|玩游戏得现金"):
            close_region = image[int(h * .78):int(h * .99), int(w * .35):int(w * .75)]
            gray = cv2.cvtColor(close_region, cv2.COLOR_BGR2GRAY)
            circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, 1.2, 80,
                                       param1=100, param2=45, minRadius=25, maxRadius=120)
            if circles is not None:
                observation.overlays.append("manor_ad")
                # Keep the close target tied to the current full-resolution
                # observation; never reuse a coordinate from an earlier ad.
                circle = max(circles[0], key=lambda item: item[2])
                cx, cy, radius = map(int, circle)
                observation.elements.append(
                    Element("广告关闭", (cx-radius, cy-radius, cx+radius, cy+radius),
                            observation.id, "vision.close_circle", 0.9)
                )
    return observation


def parse_tree(xml, observation):
    root = ET.fromstring(xml)
    elements = []
    for node in root.iter("node"):
        if node.get("enabled") == "false" or node.get("password") == "true":
            continue
        text = (node.get("text") or node.get("content-desc") or "").strip()
        values = re.findall(r"-?\d+", node.get("bounds", ""))
        if text and len(values) == 4:
            bounds = tuple(map(int, values))
            if bounds[0] < bounds[2] and bounds[1] < bounds[3]:
                elements.append(Element(text, bounds, observation, "ui_tree"))
    return elements


class Observer:
    def __init__(self, device, directory, logger):
        from rapidocr_onnxruntime import RapidOCR
        self.ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
        self.device, self.directory, self.logger = device, directory, logger
        directory.mkdir(parents=True, exist_ok=True)
        self.sequence = 0

    def capture(self, reason="observe", full=False):
        self.sequence += 1
        oid = f"{self.sequence:04d}-{uuid.uuid4().hex[:6]}"
        package = self.device.foreground()
        xml = None
        if full:
            try:
                xml = self.device.tree()
                (self.directory / (oid + ".xml")).write_bytes(xml)
            except AutomationError as exc:
                self.logger.emit("tree.unavailable", error=str(exc))
        captured = time.monotonic()
        png = self.device.screenshot()
        image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise AutomationError("Cannot decode screenshot", "DEVICE")
        h, w = image.shape[:2]
        scale = min(1.0, 1080 / w)
        small = cv2.resize(image, (round(w * scale), round(h * scale)))
        results, _ = self.ocr(small)
        elements = []
        for box, text, score in results or []:
            if score < .72:
                continue
            points = np.array(box) / scale
            bounds = (int(points[:, 0].min()), int(points[:, 1].min()),
                      int(points[:, 0].max()), int(points[:, 1].max()))
            elements.append(Element(text.strip(), bounds, oid, "ocr", float(score)))
        # OCR anchors validate XML coordinates from the separately captured tree.
        # Unmatched tree-only elements remain diagnostic until a page rule supports them.
        if xml:
            for element in parse_tree(xml, oid):
                for index, visual in enumerate(elements):
                    if element.text == visual.text and np.linalg.norm(
                        np.array(element.point) - visual.point
                    ) < 30:
                        elements[index] = Element(visual.text, visual.bounds, oid, "ui_tree+ocr", visual.score)
                        break
        obs = classify(Observation(oid, captured, w, h, package, elements, image=image))
        (self.directory / (oid + ".png")).write_bytes(png)
        payload = dict(id=oid, reason=reason, page=obs.page, overlays=obs.overlays,
                       captured=captured, package=package, width=w, height=h,
                       elements=[asdict(e) for e in elements])
        (self.directory / (oid + ".json")).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.logger.emit("observation", **payload)
        return obs
