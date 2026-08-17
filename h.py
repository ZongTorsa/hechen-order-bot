from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Playwright, TimeoutError as PlaywrightTimeoutError, sync_playwright

from config import (
    ALLOWED_DISPATCH_METHODS,
    MIN_TOTAL_PRICE,
    REQUIRED_KEYWORDS,
    SCAN_INTERVAL_SECONDS,
)


ORDER_URL = "https://www.sydg.vip/h5/#/gamePages/pei_order_pai"
ORDER_CARD_SELECTOR = ".pai_order_box"

LABEL_ORDER_ID = "\u6d3e\u5355\u53f7\uff1a"
LABEL_TOTAL_PRICE = "\u603b\u4ef7"
LABEL_PRODUCT = "\u5546\u54c1"
LABEL_REMARK = "\u5907\u6ce8"
LABEL_DISPATCH_METHOD = "\u6d3e\u5355\u65b9\u5f0f"
CONFIRM_TEXT = "\u786e\u5b9a"


@dataclass(frozen=True)
class Order:
    order_id: str
    total_price: float
    product: str
    remark: str
    dispatch_method: str


def value_after_label(lines: list[str], label: str) -> str:
    """Return the first non-empty line following a card field label."""
    try:
        return lines[lines.index(label) + 1]
    except (ValueError, IndexError):
        return ""


def parse_order(card_text: str) -> Order | None:
    """Parse one visible order card."""
    lines = [line.strip() for line in card_text.splitlines() if line.strip()]
    order_id_match = re.search(re.escape(LABEL_ORDER_ID) + r"\s*(#[^\s]+)", card_text)
    price_match = re.search(r"[\u00a5\uffe5]\s*([\d,.]+)", value_after_label(lines, LABEL_TOTAL_PRICE))

    if not order_id_match or not price_match:
        return None

    return Order(
        order_id=order_id_match.group(1),
        total_price=float(price_match.group(1).replace(",", "")),
        product=value_after_label(lines, LABEL_PRODUCT),
        remark=value_after_label(lines, LABEL_REMARK),
        dispatch_method=value_after_label(lines, LABEL_DISPATCH_METHOD),
    )


def contains_any(text: str, keywords: list[str]) -> str | None:
    """Return the first matched keyword, otherwise None."""
    normalized_text = text.casefold()
    for keyword in keywords:
        normalized_keyword = keyword.strip()
        if normalized_keyword and normalized_keyword.casefold() in normalized_text:
            return normalized_keyword
    return None


def evaluate_order(order: Order) -> list[str]:
    """Return rejection reasons. No reasons means this order may be grabbed."""
    reasons: list[str] = []

    if order.total_price < MIN_TOTAL_PRICE:
        reasons.append(f"总价 {order.total_price:.2f} 低于最低总价 {MIN_TOTAL_PRICE:.2f}")

    required_keywords = [keyword.strip() for keyword in REQUIRED_KEYWORDS if keyword.strip()]
    if not required_keywords:
        reasons.append("未配置关键词白名单，当前不会抢单")
    else:
        keyword = contains_any(f"{order.product}\n{order.remark}", required_keywords)
        if keyword is None:
            reasons.append("商品和备注均未命中关键词白名单")

    allowed_methods = [method.strip() for method in ALLOWED_DISPATCH_METHODS if method.strip()]
    if allowed_methods and order.dispatch_method not in allowed_methods:
        reasons.append(f"派单方式 {order.dispatch_method!r} 不在允许列表中")

    return reasons


def print_order_result(order: Order, reasons: list[str]) -> None:
    print("\n" + "=" * 50)
    print(f"派单号：{order.order_id}")
    print(f"总价：{order.total_price:.2f}")
    print(f"商品：{order.product}")
    print(f"备注：{order.remark}")
    print(f"派单方式：{order.dispatch_method}")

    if reasons:
        print("结果：跳过")
        for reason in reasons:
            print(f"- {reason}")
    else:
        print("结果：符合规则，即将抢当前订单")


def click_grab_button(page, order: Order, detected_card_index: int) -> bool:
    """Click the button and confirmation belonging to this exact order card."""
    matching_card = page.locator(ORDER_CARD_SELECTOR).filter(has_text=order.order_id)
    matching_count = matching_card.count()
    if matching_count != 1:
        print(f"[抢单跳过] {order.order_id}：匹配到 {matching_count} 张订单卡片")
        return False

    current_order = parse_order(matching_card.inner_text())
    if current_order is None or current_order.order_id != order.order_id:
        print(f"[抢单跳过] {order.order_id}：点击前订单卡片内容已变化")
        return False

    grab_button = matching_card.locator(".pai_order_button")
    if grab_button.count() != 1:
        print(f"[抢单跳过] {order.order_id}：该订单卡片内的抢单按钮数量不为 1")
        return False

    print(f"[开始抢单] 派单号：{order.order_id}，当前页面卡片序号：{detected_card_index + 1}")
    grab_button.click()

    confirm_button = page.get_by_text(CONFIRM_TEXT, exact=True)
    try:
        confirm_button.wait_for(state="visible", timeout=5_000)
    except PlaywrightTimeoutError:
        print(f"[抢单未确认] {order.order_id}：5 秒内未找到“确定”按钮")
        return False

    if confirm_button.count() != 1:
        print(f"[抢单未确认] {order.order_id}：“确定”按钮数量不为 1，未点击")
        return False

    confirm_button.click()
    print(f"[抢单已确认] {order.order_id}")
    return True


def run(playwright: Playwright) -> None:
    profile_dir = Path(__file__).parent / "playwright-profile"
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        channel="chrome",
        headless=False,
    )

    page = context.pages[0] if context.pages else context.new_page()
    page.goto(ORDER_URL, wait_until="domcontentloaded")

    seen_order_ids: set[str] = set()
    interval_ms = max(100, int(SCAN_INTERVAL_SECONDS * 1000))
    was_empty = False
    print(f"订单监控已启动，检测间隔：{SCAN_INTERVAL_SECONDS} 秒。按 Ctrl + C 停止。")

    try:
        while True:
            card_texts = page.locator(ORDER_CARD_SELECTOR).all_inner_texts()

            if not card_texts:
                if not was_empty:
                    print("当前没有订单，继续监控中。")
                was_empty = True
                page.wait_for_timeout(interval_ms)
                continue

            was_empty = False
            for index, card_text in enumerate(card_texts):
                order = parse_order(card_text)
                if order is None or order.order_id in seen_order_ids:
                    continue

                seen_order_ids.add(order.order_id)
                reasons = evaluate_order(order)
                print_order_result(order, reasons)
                if not reasons:
                    click_grab_button(page, order, index)
                    page.wait_for_timeout(500)

            page.wait_for_timeout(interval_ms)
    except KeyboardInterrupt:
        print("\n订单监控已停止。")
    finally:
        context.close()


if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)
