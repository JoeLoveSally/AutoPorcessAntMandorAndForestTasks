import cv2
import numpy as np

from domain_data import Element


def quiz_options(obs):
    hsv = cv2.cvtColor(obs.image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 35, 130), (179, 255, 255))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x,y,w,h = cv2.boundingRect(contour)
        if w > obs.width*.5 and obs.height*.025 < h < obs.height*.12 and obs.height*.25 < y < obs.height*.85:
            texts = [e for e in obs.elements if x < e.point[0] < x+w and y < e.point[1] < y+h]
            if texts:
                boxes.append(Element(" ".join(e.text for e in texts), (x,y,x+w,y+h), obs.id, "ocr+geometry"))
    return sorted(boxes, key=lambda e:e.point[1])


def energy_balls(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array((30,90,120)), np.array((90,255,255)))
    h,w = mask.shape
    mask[:int(.12*h)] = 0
    mask[int(.85*h):] = 0
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    result = []
    for contour in contours:
        area = cv2.contourArea(contour)
        x,y,bw,bh = cv2.boundingRect(contour)
        if .00012*w*h < area < .006*w*h and .6 < bw/max(bh,1) < 1.6:
            result.append((x+bw//2,y+bh//2))
    return result
