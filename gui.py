#!/usr/bin/env python3
"""Desktop GUI for configuring and creating App Store Connect subscription SKUs."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from argparse import Namespace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

import customtkinter as ctk

from sku_io import dump_skus, load_skus, merge_skus, write_excel_template, write_json_template
from create_subscriptions import (
    ASCClient,
    ASCError,
    Catalog,
    CreateOptions,
    PAYG_DURATION_BY_PERIOD,
    PROJECT_DIR,
    bundled_root,
    catalog_from_dict,
    catalog_to_dict,
    create_from_catalog,
    data_dir,
    discover_p8,
    fetch_apps,
    fetch_groups,
    fetch_skus,
    format_errors,
    key_id_from_p8_name,
    load_auth,
    load_catalog,
    load_env_file,
    merge_local_sku_with_asc,
    save_catalog,
    save_credentials,
    scaffold_catalog,
    seed_user_data,
    sku_dict_from_asc_row,
    store_review_screenshot,
)

PERIOD_CHOICES = (
    ("ONE_WEEK", "1 周"),
    ("ONE_MONTH", "1 个月"),
    ("TWO_MONTHS", "2 个月"),
    ("THREE_MONTHS", "3 个月"),
    ("SIX_MONTHS", "6 个月"),
    ("ONE_YEAR", "1 年"),
)
INTRO_MODE_CHOICES = (
    ("", "无"),
    ("PAY_AS_YOU_GO", "随用随付"),
    ("PAY_UP_FRONT", "提前支付"),
    ("FREE_TRIAL", "免费"),
)
FREE_DURATION_CHOICES = (
    ("THREE_DAYS", "3 天"),
    ("ONE_WEEK", "1 周"),
    ("TWO_WEEKS", "2 周"),
    ("ONE_MONTH", "1 个月"),
    ("TWO_MONTHS", "2 个月"),
    ("THREE_MONTHS", "3 个月"),
    ("SIX_MONTHS", "6 个月"),
    ("ONE_YEAR", "1 年"),
)
PAY_UP_FRONT_DURATION_CHOICES = (
    ("ONE_MONTH", "1 个月"),
    ("TWO_MONTHS", "2 个月"),
    ("THREE_MONTHS", "3 个月"),
    ("SIX_MONTHS", "6 个月"),
    ("ONE_YEAR", "1 年"),
)
INTRO_DURATION_CHOICES = FREE_DURATION_CHOICES
DURATION_PLACEHOLDER = "选取"
PAYG_PERIOD_COUNTS = tuple(str(index) for index in range(1, 13))
PAYG_UNIT_LABELS = {
    "ONE_WEEK": "周数",
    "ONE_MONTH": "月数",
    "TWO_MONTHS": "期数",
    "THREE_MONTHS": "期数",
    "SIX_MONTHS": "期数",
    "ONE_YEAR": "年数",
}
PAYG_EACH_LABEL = {
    "ONE_WEEK": "每周",
    "ONE_MONTH": "每月",
    "TWO_MONTHS": "每 2 个月",
    "THREE_MONTHS": "每 3 个月",
    "SIX_MONTHS": "每 6 个月",
    "ONE_YEAR": "每年",
}
PAYG_FIRST_LABEL = {
    "ONE_WEEK": "首周",
    "ONE_MONTH": "首月",
    "ONE_YEAR": "首年",
}
PAYG_COUNT_SUFFIX = {
    "ONE_WEEK": "周",
    "ONE_MONTH": "个月",
    "TWO_MONTHS": "期",
    "THREE_MONTHS": "期",
    "SIX_MONTHS": "期",
    "ONE_YEAR": "年",
}
PAY_UP_FRONT_SUMMARY = {
    "ONE_MONTH": "首月 {price}",
    "TWO_MONTHS": "前 2 个月 {price}",
    "THREE_MONTHS": "前 3 个月 {price}",
    "SIX_MONTHS": "前 6 个月 {price}",
    "ONE_YEAR": "首年 {price}",
}
PRICE_SCOPE_CHOICES = (
    ("usa", "仅美国"),
    ("all", "所有店面"),
)
STATE_CHOICES = (
    ("MISSING_METADATA", "缺少元数据"),
    ("READY_TO_SUBMIT", "准备提交"),
    ("WAITING_FOR_REVIEW", "正在等待审核"),
    ("IN_REVIEW", "正在审核"),
    ("DEVELOPER_ACTION_NEEDED", "需要开发者操作"),
    ("PENDING_BINARY_APPROVAL", "正在等待二进制文件批准"),
    ("APPROVED", "已批准"),
    ("DEVELOPER_REMOVED_FROM_SALE", "开发者已从销售中移除"),
    ("REMOVED_FROM_SALE", "已从销售中移除"),
    ("REJECTED", "被拒绝"),
)
LOCALE_CHOICES = (
    ("ar-SA", "阿拉伯语"),
    ("bn-BD", "孟加拉语"),
    ("ca", "加泰罗尼亚语"),
    ("zh-Hans", "简体中文"),
    ("zh-Hant", "繁体中文"),
    ("hr", "克罗地亚语"),
    ("cs", "捷克语"),
    ("da", "丹麦语"),
    ("nl-NL", "荷兰语"),
    ("en-AU", "英语（澳大利亚）"),
    ("en-CA", "英语（加拿大）"),
    ("en-GB", "英语（英国）"),
    ("en-US", "英语（美国）"),
    ("fi", "芬兰语"),
    ("fr-FR", "法语"),
    ("fr-CA", "法语（加拿大）"),
    ("de-DE", "德语"),
    ("el", "希腊语"),
    ("gu-IN", "古吉拉特语"),
    ("he", "希伯来语"),
    ("hi", "印地语"),
    ("hu", "匈牙利语"),
    ("id", "印度尼西亚语"),
    ("it", "意大利语"),
    ("ja", "日语"),
    ("kn-IN", "卡纳达语"),
    ("ko", "韩语"),
    ("ms", "马来语"),
    ("ml-IN", "马拉雅拉姆语"),
    ("mr-IN", "马拉地语"),
    ("no", "挪威语"),
    ("or-IN", "奥里亚语"),
    ("pl", "波兰语"),
    ("pt-BR", "葡萄牙语（巴西）"),
    ("pt-PT", "葡萄牙语（葡萄牙）"),
    ("pa-IN", "旁遮普语"),
    ("ro", "罗马尼亚语"),
    ("ru", "俄语"),
    ("sk", "斯洛伐克语"),
    ("sl-SI", "斯洛文尼亚语"),
    ("es-MX", "西班牙语（墨西哥）"),
    ("es-ES", "西班牙语（西班牙）"),
    ("sv", "瑞典语"),
    ("ta-IN", "泰米尔语"),
    ("te-IN", "泰卢固语"),
    ("th", "泰语"),
    ("tr", "土耳其语"),
    ("uk", "乌克兰语"),
    ("ur-PK", "乌尔都语"),
    ("vi", "越南语"),
)

SKU_FIELD_HINTS = {
    "product_id": "创建后不可修改，如 dj.month.1.0",
    "reference_name": "App Store Connect 内部名称，最多 64 个字符",
    "period": "1 周、1 个月、2 个月、3 个月、6 个月、1 年",
    "usd_price": "美国店面标价，美元，如 29.99",
    "intro_mode": "随用随付、提前支付、免费；没有则选「无」",
    "intro_duration": "免费：3 天～1 年；提前支付：1 个月～1 年；随用随付选 1–12 个计费周期",
    "intro_usd": "随用随付或提前支付时填写；免费请留空",
    "review_note": "仅 App 审核人员可见，每个 SKU 单独填写，可留空",
    "review_screenshot": "SKU 页面审核截图，JPG 或 PNG，可留空",
    "prefix": "产品 ID 前缀，如 dj 或 com.example.vip",
    "name_prefix": "参考名称前缀，如 vip",
    "version": "同一期限下的版本号，如 1",
    "intro_usd_matrix": "矩阵里「随用随付」档的美元价",
}


def choice_labels(choices: tuple[tuple[str, str], ...]) -> list[str]:
    return [label for _code, label in choices]


def choice_label(choices: tuple[tuple[str, str], ...], value: str, fallback: str = "") -> str:
    compact = value.strip().replace(" ", "")
    aliases = {"预付": "PAY_UP_FRONT", "提前付款": "PAY_UP_FRONT", "免费试用": "FREE_TRIAL"}
    value = aliases.get(value.strip(), value)
    compact = aliases.get(compact, compact)
    for code, label in choices:
        if value in {code, label} or compact in {code, label.replace(" ", "")}:
            return label
    return fallback or value


def choice_value(choices: tuple[tuple[str, str], ...], selected: str, fallback: str = "") -> str:
    selected = selected.strip()
    compact = selected.replace(" ", "")
    aliases = {"预付": "PAY_UP_FRONT", "提前付款": "PAY_UP_FRONT", "免费试用": "FREE_TRIAL"}
    if selected in aliases or compact in aliases:
        return aliases.get(selected) or aliases[compact]
    for code, label in choices:
        if selected in {code, label} or compact in {code, label.replace(" ", "")}:
            return code
    return fallback


def format_intro_text(intro: dict[str, Any] | None, period: str = "") -> str:
    if not intro:
        return "无"
    mode = str(intro.get("mode", ""))
    if mode == "PAY_AS_YOU_GO":
        count = intro.get("number_of_periods") or 1
        suffix = PAYG_COUNT_SUFFIX.get(period, "期")
        text = f"随用随付 · {count} {suffix}"
    elif mode == "PAY_UP_FRONT":
        duration = choice_label(PAY_UP_FRONT_DURATION_CHOICES, str(intro.get("duration", "")), "")
        text = f"提前支付 · {duration}"
    elif mode == "FREE_TRIAL":
        duration = choice_label(FREE_DURATION_CHOICES, str(intro.get("duration", "")), "")
        text = f"免费 · {duration}"
    else:
        return "无"
    if intro.get("usd_price"):
        text += f" · ${intro['usd_price']}"
    return text


def next_group_level(skus: list[dict[str, Any]]) -> int:
    levels: list[int] = []
    for sku in skus:
        raw = sku.get("group_level")
        if raw in (None, ""):
            continue
        try:
            levels.append(int(raw))
        except (TypeError, ValueError):
            continue
    return max(levels) + 1 if levels else 1


def format_usd_price(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    if text.startswith("$"):
        return text
    return f"${text}"


def asc_intro_summary(mode: str, period: str, selected: str, price: str) -> str:
    if not mode or selected in {"", DURATION_PLACEHOLDER}:
        return ""
    usd = format_usd_price(price)
    if mode == "FREE_TRIAL":
        return f"{selected}免费试用"
    if not usd:
        return ""
    if mode == "PAY_UP_FRONT":
        duration = choice_value(PAY_UP_FRONT_DURATION_CHOICES, selected, "")
        template = PAY_UP_FRONT_SUMMARY.get(duration)
        return template.format(price=usd) if template else f"{selected} {usd}"
    if mode != "PAY_AS_YOU_GO":
        return ""
    try:
        count = int(selected)
    except ValueError:
        return ""
    first = PAYG_FIRST_LABEL.get(period)
    each = PAYG_EACH_LABEL.get(period, "每期")
    if count == 1 and first:
        return f"{first} {usd}"
    if count == 1:
        unit = choice_label(PERIOD_CHOICES, period, "")
        return f"前 {unit} {usd}" if unit else f"{each} {usd}"
    return f"前 {count} 周期间{each} {usd}"


def intro_offer_display(intro: dict[str, Any], period: str) -> str:
    mode = str(intro.get("mode", ""))
    if mode == "PAY_AS_YOU_GO":
        return str(intro.get("number_of_periods") or 1)
    if mode == "PAY_UP_FRONT":
        return choice_label(PAY_UP_FRONT_DURATION_CHOICES, str(intro.get("duration", "ONE_MONTH")), "1 个月")
    if mode == "FREE_TRIAL":
        return choice_label(FREE_DURATION_CHOICES, str(intro.get("duration", "THREE_DAYS")), "3 天")
    return ""

def confirm_delete(parent: tk.Misc | None, title: str, detail: str) -> bool:
    return bool(messagebox.askyesno(title, f"确定删除{detail}？此操作不可撤销。", parent=parent, icon="warning"))


ACCENT = "#0A84FF"
ACCENT_HOVER = "#409CFF"
DANGER = "#FF453A"
SIDEBAR = "#101218"
CARD = "#1C2028"
MUTED = "#8E8E93"


class TextRedirect:
    def __init__(self, write_fn: Callable[[str], None]) -> None:
        self._write_fn = write_fn

    def write(self, text: str) -> None:
        if text:
            self._write_fn(text)

    def flush(self) -> None:
        return None


class FormDialog(ctk.CTkToplevel):
    def __init__(self, master: tk.Misc, title: str, size: str) -> None:
        super().__init__(master)
        self.title(title)
        self.geometry(size)
        self.resizable(False, False)
        self.result: dict[str, Any] | None = None
        self.transient(master)
        self.after(20, self._front)

    def _front(self) -> None:
        self.lift()
        self.focus()
        self.grab_set()

    def _row(
        self,
        parent: ctk.CTkFrame,
        row: int,
        label: str,
        widget: ctk.CTkBaseClass,
        hint: str | None = None,
        labelvariable: tk.StringVar | None = None,
        hintvariable: tk.StringVar | None = None,
        hint_widget: ctk.CTkBaseClass | None = None,
    ) -> None:
        field_row = row * 2
        hint_row = row * 2 + 1
        show_hint = bool(hint or hintvariable or hint_widget)
        label_kwargs: dict[str, Any] = {"width": 140, "anchor": "w"}
        if labelvariable is not None:
            label_kwargs["textvariable"] = labelvariable
            label_kwargs["text"] = ""
        else:
            label_kwargs["text"] = label
        ctk.CTkLabel(parent, **label_kwargs).grid(
            row=field_row,
            column=0,
            rowspan=2 if show_hint else 1,
            sticky="nw",
            pady=(8, 6),
            padx=(0, 12),
        )
        widget.grid(row=field_row, column=1, sticky="ew", pady=(8, 2))
        if hint_widget is not None:
            hint_widget.grid(row=hint_row, column=1, sticky="ew", pady=(0, 6))
        elif show_hint:
            hint_kwargs: dict[str, Any] = {
                "text_color": MUTED,
                "font": ctk.CTkFont(size=11),
                "anchor": "w",
                "wraplength": 360,
                "justify": "left",
            }
            if hintvariable is not None:
                hint_kwargs["textvariable"] = hintvariable
                hint_kwargs["text"] = hint or ""
            else:
                hint_kwargs["text"] = hint or ""
            ctk.CTkLabel(parent, **hint_kwargs).grid(row=hint_row, column=1, sticky="ew", pady=(0, 6))


class ActionDialog(FormDialog):
    def __init__(self, master: tk.Misc, title: str, hint: str, actions: tuple[tuple[str, str], ...]) -> None:
        height = 160 + 42 * (len(actions) + 1)
        super().__init__(master, title, f"440x{height}")
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=16)
        ctk.CTkLabel(body, text=hint, text_color=MUTED, wraplength=400, justify="left", anchor="w").pack(fill="x", pady=(0, 12))
        for text, action in actions:
            ctk.CTkButton(
                body,
                text=text,
                height=34,
                fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
                command=lambda value=action: self._choose(value),
            ).pack(fill="x", pady=4)
        ctk.CTkButton(body, text="取消", height=34, fg_color="#3A3A3C", hover_color="#48484A", command=self.destroy).pack(
            fill="x", pady=(8, 0)
        )

    def _choose(self, action: str) -> None:
        self.result = {"action": action}
        self.destroy()


class SKUDialog(FormDialog):
    def __init__(self, master: tk.Misc, sku: dict[str, Any] | None = None, *, next_level: int = 1) -> None:
        super().__init__(master, "SKU", "560x1")
        self.resizable(False, False)
        sku = sku or {}
        self.source_sku = sku
        intro = sku.get("intro") or {}
        period_code = str(sku.get("period", "ONE_MONTH"))
        self.existing_level = sku.get("group_level")
        self.next_level = next_level
        self.vars = {
            "product_id": tk.StringVar(value=str(sku.get("product_id", ""))),
            "reference_name": tk.StringVar(value=str(sku.get("reference_name", ""))),
            "period": tk.StringVar(value=choice_label(PERIOD_CHOICES, period_code, "1 个月")),
            "usd_price": tk.StringVar(value=str(sku.get("usd_price", ""))),
            "intro_mode": tk.StringVar(value=choice_label(INTRO_MODE_CHOICES, str(intro.get("mode", "")), "无")),
            "intro_offer": tk.StringVar(value=intro_offer_display(intro, period_code) or DURATION_PLACEHOLDER),
            "intro_usd": tk.StringVar(value=str(intro.get("usd_price", ""))),
            "review_note": tk.StringVar(value=str(sku.get("review_note") or "")),
            "review_screenshot": tk.StringVar(value=str(sku.get("review_screenshot") or "")),
        }
        self.duration_hint_var = tk.StringVar(value=SKU_FIELD_HINTS["intro_duration"])
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="x", padx=20, pady=16)
        body.grid_columnconfigure(1, weight=1)
        rows: list[tuple[str, str, tuple[tuple[str, str], ...] | None, str | None]] = [
            ("产品 ID", "product_id", None, SKU_FIELD_HINTS["product_id"]),
            ("参考名称", "reference_name", None, SKU_FIELD_HINTS["reference_name"]),
            ("订阅期限", "period", PERIOD_CHOICES, SKU_FIELD_HINTS["period"]),
            ("美区价格", "usd_price", None, SKU_FIELD_HINTS["usd_price"]),
            ("推介促销优惠类型", "intro_mode", INTRO_MODE_CHOICES, SKU_FIELD_HINTS["intro_mode"]),
            ("持续时间", "intro_offer", FREE_DURATION_CHOICES, SKU_FIELD_HINTS["intro_duration"]),
            ("价格", "intro_usd", None, SKU_FIELD_HINTS["intro_usd"]),
        ]
        placeholders = {
            "product_id": "dj.month.1.0",
            "reference_name": "vip month 1.0",
            "usd_price": "29.99",
            "intro_usd": "9.99",
        }
        self.duration_box: ctk.CTkComboBox | None = None
        for index, (label, key, choices, hint) in enumerate(rows):
            if choices is None:
                widget: ctk.CTkBaseClass = ctk.CTkEntry(
                    body,
                    textvariable=self.vars[key],
                    height=32,
                    placeholder_text=placeholders.get(key, ""),
                )
            else:
                combo_kwargs: dict[str, Any] = {
                    "variable": self.vars[key],
                    "values": (
                        [DURATION_PLACEHOLDER, *choice_labels(FREE_DURATION_CHOICES)]
                        if key == "intro_offer"
                        else choice_labels(choices)
                    ),
                    "state": "readonly",
                    "height": 32,
                    "width": 320,
                }
                if key in {"period", "intro_mode", "intro_offer"}:
                    combo_kwargs["command"] = self._refresh_intro_fields
                widget = ctk.CTkComboBox(body, **combo_kwargs)
                if key == "intro_offer":
                    self.duration_box = widget
            if key == "intro_offer":
                self._row(body, index, label, widget, hintvariable=self.duration_hint_var)
            elif key == "intro_usd":
                self.price_summary_var = tk.StringVar(value="")
                price_hint = ctk.CTkFrame(body, fg_color="transparent")
                ctk.CTkLabel(
                    price_hint,
                    text=hint or "",
                    text_color=MUTED,
                    font=ctk.CTkFont(size=11),
                    anchor="w",
                    wraplength=360,
                    justify="left",
                ).pack(fill="x")
                ctk.CTkLabel(
                    price_hint,
                    textvariable=self.price_summary_var,
                    text_color=ACCENT,
                    font=ctk.CTkFont(size=12),
                    anchor="w",
                    height=18,
                    wraplength=360,
                    justify="left",
                ).pack(fill="x", pady=(2, 0))
                self._row(body, index, label, widget, hint_widget=price_hint)
            else:
                self._row(body, index, label, widget, hint)
        extra_index = len(rows)
        self._row(
            body,
            extra_index,
            "审核备注",
            ctk.CTkEntry(
                body,
                textvariable=self.vars["review_note"],
                height=32,
                placeholder_text="给审核人员看的说明",
            ),
            SKU_FIELD_HINTS["review_note"],
        )
        shot_row = ctk.CTkFrame(body, fg_color="transparent")
        shot_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(
            shot_row,
            textvariable=self.vars["review_screenshot"],
            height=32,
            placeholder_text="选择 JPG 或 PNG",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            shot_row,
            text="选择",
            width=64,
            height=32,
            fg_color="#3A3A3C",
            hover_color="#48484A",
            command=self._browse_screenshot,
        ).grid(row=0, column=1)
        self._row(body, extra_index + 1, "审核截图", shot_row, SKU_FIELD_HINTS["review_screenshot"])
        self.vars["intro_usd"].trace_add("write", lambda *_args: self._update_price_summary())
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.grid(row=(extra_index + 2) * 2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ctk.CTkButton(buttons, text="取消", fg_color="#3A3A3C", hover_color="#48484A", width=88, command=self.destroy).pack(
            side="right", padx=(8, 0)
        )
        ctk.CTkButton(buttons, text="确定", width=88, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._confirm).pack(
            side="right"
        )
        self._refresh_intro_fields()
        self.update_idletasks()
        height = body.winfo_reqheight() + 36
        self.geometry(f"560x{height}")
        self.minsize(560, height)

    def _duration_values(self, mode: str) -> list[str]:
        if mode == "PAY_AS_YOU_GO":
            options = list(PAYG_PERIOD_COUNTS)
        elif mode == "PAY_UP_FRONT":
            options = choice_labels(PAY_UP_FRONT_DURATION_CHOICES)
        else:
            options = choice_labels(FREE_DURATION_CHOICES)
        return [DURATION_PLACEHOLDER, *options]

    def _refresh_intro_fields(self, _selected: str | None = None) -> None:
        if self.duration_box is None:
            return
        mode = choice_value(INTRO_MODE_CHOICES, self.vars["intro_mode"].get(), "")
        values = self._duration_values(mode)
        current = self.vars["intro_offer"].get().strip()
        self.duration_box.configure(values=values)
        if not mode or current not in values:
            self.vars["intro_offer"].set(DURATION_PLACEHOLDER)
        if mode == "PAY_AS_YOU_GO":
            period = choice_value(PERIOD_CHOICES, self.vars["period"].get(), "ONE_MONTH")
            unit = PAYG_UNIT_LABELS.get(period, "期数")
            self.duration_hint_var.set(f"随用随付选 1–12 个{unit}；必须与订阅期限相同")
        elif mode == "PAY_UP_FRONT":
            self.duration_hint_var.set("提前支付：1 个月、2 个月、3 个月、6 个月、1 年")
        elif mode == "FREE_TRIAL":
            self.duration_hint_var.set("免费：3 天、1 周、2 周、1 个月、2 个月、3 个月、6 个月、1 年")
        else:
            self.duration_hint_var.set(SKU_FIELD_HINTS["intro_duration"])
        self._update_price_summary()

    def _update_price_summary(self) -> None:
        if not hasattr(self, "price_summary_var"):
            return
        mode = choice_value(INTRO_MODE_CHOICES, self.vars["intro_mode"].get(), "")
        period = choice_value(PERIOD_CHOICES, self.vars["period"].get(), "ONE_MONTH")
        selected = self.vars["intro_offer"].get().strip()
        price = self.vars["intro_usd"].get().strip()
        summary = asc_intro_summary(mode, period, selected, price)
        self.price_summary_var.set(f"ⓘ  {summary}" if summary else "")

    def _browse_screenshot(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 SKU 审核截图",
            filetypes=[("Images", "*.png *.jpg *.jpeg"), ("All files", "*.*")],
            parent=self,
        )
        if path:
            self.vars["review_screenshot"].set(path)

    def _confirm(self) -> None:
        product_id = self.vars["product_id"].get().strip()
        reference_name = self.vars["reference_name"].get().strip()
        usd_price = self.vars["usd_price"].get().strip()
        if not product_id or not reference_name or not usd_price:
            messagebox.showerror("SKU", "产品 ID、参考名称和美区价格不能为空。", parent=self)
            return
        payload: dict[str, Any] = {
            "product_id": product_id,
            "reference_name": reference_name,
            "period": choice_value(PERIOD_CHOICES, self.vars["period"].get(), "ONE_MONTH"),
            "usd_price": usd_price,
            "group_level": int(self.existing_level) if self.existing_level not in (None, "") else self.next_level,
        }
        mode = choice_value(INTRO_MODE_CHOICES, self.vars["intro_mode"].get(), "")
        if mode:
            selected = self.vars["intro_offer"].get().strip()
            if not selected or selected == DURATION_PLACEHOLDER:
                messagebox.showerror("SKU", "请选择持续时间。", parent=self)
                return
            if mode == "PAY_AS_YOU_GO":
                try:
                    periods = int(selected)
                except ValueError:
                    messagebox.showerror("SKU", "请选择随用随付的持续时间。", parent=self)
                    return
                intro: dict[str, Any] = {
                    "mode": mode,
                    "duration": PAYG_DURATION_BY_PERIOD.get(payload["period"], payload["period"]),
                    "number_of_periods": periods,
                }
            elif mode == "PAY_UP_FRONT":
                intro = {
                    "mode": mode,
                    "duration": choice_value(PAY_UP_FRONT_DURATION_CHOICES, selected, "ONE_MONTH"),
                    "number_of_periods": 1,
                }
            else:
                intro = {
                    "mode": mode,
                    "duration": choice_value(FREE_DURATION_CHOICES, selected, "THREE_DAYS"),
                    "number_of_periods": 1,
                }
            intro_usd = self.vars["intro_usd"].get().strip()
            if mode in {"PAY_AS_YOU_GO", "PAY_UP_FRONT"} and not intro_usd:
                messagebox.showerror("SKU", "随用随付和提前支付需要填写价格。", parent=self)
                return
            if intro_usd and mode != "FREE_TRIAL":
                intro["usd_price"] = intro_usd
            payload["intro"] = intro
        if self.source_sku.get("state"):
            payload["state"] = self.source_sku["state"]
        review_note = self.vars["review_note"].get().strip()
        if review_note:
            payload["review_note"] = review_note
        screenshot = self.vars["review_screenshot"].get().strip()
        if screenshot:
            try:
                payload["review_screenshot"] = store_review_screenshot(product_id, screenshot)
            except ASCError as error:
                messagebox.showerror("SKU", str(error), parent=self)
                return
        self.result = payload
        self.destroy()


class LocalizationDialog(FormDialog):
    def __init__(self, master: tk.Misc, item: dict[str, str] | None = None) -> None:
        super().__init__(master, "本地化", "520x340")
        item = item or {}
        self.locale = tk.StringVar(value=choice_label(LOCALE_CHOICES, str(item.get("locale", "en-US")), "英语（美国）"))
        self.name = tk.StringVar(value=str(item.get("name", "")))
        self.description = tk.StringVar(value=str(item.get("description", "")))
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=16)
        body.grid_columnconfigure(1, weight=1)
        self._row(
            body,
            0,
            "语言",
            ctk.CTkComboBox(
                body,
                variable=self.locale,
                values=choice_labels(LOCALE_CHOICES),
                state="readonly",
                height=32,
                width=280,
            ),
            "订阅页显示语言，覆盖 App Store 全部 50 种本地化",
        )
        self._row(
            body,
            1,
            "显示名称",
            ctk.CTkEntry(body, textvariable=self.name, height=32, placeholder_text="VIP Monthly"),
            "用户在订阅页看到的名称",
        )
        self._row(
            body,
            2,
            "描述",
            ctk.CTkEntry(body, textvariable=self.description, height=32, placeholder_text="Unlock all episodes"),
            "订阅说明，可留空",
        )
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ctk.CTkButton(buttons, text="取消", fg_color="#3A3A3C", hover_color="#48484A", width=88, command=self.destroy).pack(
            side="right", padx=(8, 0)
        )
        ctk.CTkButton(buttons, text="确定", width=88, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._confirm).pack(
            side="right"
        )

    def _confirm(self) -> None:
        locale = choice_value(LOCALE_CHOICES, self.locale.get(), self.locale.get().strip())
        name = self.name.get().strip()
        if not locale or not name:
            messagebox.showerror("本地化", "语言和显示名称不能为空。", parent=self)
            return
        self.result = {"locale": locale, "name": name, "description": self.description.get().strip()}
        self.destroy()


class MatrixDialog(FormDialog):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, "生成 SKU 矩阵", "540x620")
        self.resizable(False, True)
        self.vars = {
            "prefix": tk.StringVar(),
            "name_prefix": tk.StringVar(),
            "period": tk.StringVar(value="1 个月"),
            "version": tk.StringVar(value="1"),
            "usd_price": tk.StringVar(),
            "intro_usd": tk.StringVar(),
        }
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=16)
        body.grid_columnconfigure(1, weight=1)
        rows: list[tuple[str, str, tuple[tuple[str, str], ...] | None, str]] = [
            ("产品 ID 前缀", "prefix", None, SKU_FIELD_HINTS["prefix"]),
            ("参考名前缀", "name_prefix", None, SKU_FIELD_HINTS["name_prefix"]),
            ("订阅期限", "period", PERIOD_CHOICES, SKU_FIELD_HINTS["period"]),
            ("版本号", "version", None, SKU_FIELD_HINTS["version"]),
            ("美区价格", "usd_price", None, SKU_FIELD_HINTS["usd_price"]),
            ("随用随付价格", "intro_usd", None, SKU_FIELD_HINTS["intro_usd_matrix"]),
        ]
        placeholders = {
            "prefix": "dj",
            "name_prefix": "vip",
            "version": "1",
            "usd_price": "29.99",
            "intro_usd": "9.99",
        }
        for index, (label, key, choices, hint) in enumerate(rows):
            if choices is None:
                widget: ctk.CTkBaseClass = ctk.CTkEntry(
                    body,
                    textvariable=self.vars[key],
                    height=32,
                    placeholder_text=placeholders.get(key, ""),
                )
            else:
                widget = ctk.CTkComboBox(
                    body,
                    variable=self.vars[key],
                    values=choice_labels(choices),
                    state="readonly",
                    height=32,
                    width=280,
                )
            self._row(body, index, label, widget, hint)
        ctk.CTkLabel(
            body,
            text="默认生成 4 档：无试用 / 前三天免费 / 随用随付 / 首周免费。已存在的产品 ID 会跳过。",
            text_color=MUTED,
            wraplength=420,
            justify="left",
        ).grid(row=len(rows) * 2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.grid(row=len(rows) * 2 + 1, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ctk.CTkButton(buttons, text="取消", fg_color="#3A3A3C", hover_color="#48484A", width=88, command=self.destroy).pack(
            side="right", padx=(8, 0)
        )
        ctk.CTkButton(buttons, text="生成", width=88, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._confirm).pack(
            side="right"
        )

    def _confirm(self) -> None:
        prefix = self.vars["prefix"].get().strip()
        name_prefix = self.vars["name_prefix"].get().strip()
        usd_price = self.vars["usd_price"].get().strip()
        intro_usd = self.vars["intro_usd"].get().strip()
        if not prefix or not name_prefix or not usd_price:
            messagebox.showerror("生成矩阵", "前缀、参考名前缀和美区价格不能为空。", parent=self)
            return
        if not intro_usd:
            messagebox.showerror("生成矩阵", "默认矩阵包含随用随付档，请填写随用随付价格。", parent=self)
            return
        try:
            version = int(self.vars["version"].get().strip() or 1)
        except ValueError:
            messagebox.showerror("生成矩阵", "版本号必须是整数。", parent=self)
            return
        self.result = {
            "prefix": prefix,
            "name_prefix": name_prefix,
            "period": choice_value(PERIOD_CHOICES, self.vars["period"].get(), "ONE_MONTH"),
            "version": version,
            "usd_price": usd_price,
            "intro_usd": intro_usd,
        }
        self.destroy()


class App:
    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        self.root.title("ASC SKU")
        self.root.geometry("1280x840")
        self.root.minsize(1100, 720)
        self.client: ASCClient | None = None
        self.apps: list[dict[str, str]] = []
        self.groups: list[dict[str, str]] = []
        self.project_path: Path | None = None
        self.skus: list[dict[str, Any]] = []
        self.localizations: list[dict[str, str]] = []
        self.saved_app_id = ""
        self.saved_bundle_id = ""
        self.busy = False

        self.issuer = tk.StringVar()
        self.key_id = tk.StringVar()
        self.p8_path = tk.StringVar()
        self.project_name = tk.StringVar()
        self.app_choice = tk.StringVar()
        self.group_choice = tk.StringVar()
        self.group_id = tk.StringVar()
        self.base_territory = tk.StringVar(value="USA")
        self.price_scope = tk.StringVar(value="所有店面")
        self.family_sharable = tk.BooleanVar(value=False)
        self.available_in_all = tk.BooleanVar(value=True)
        self.fill_missing = tk.BooleanVar(value=False)
        self.nearest_price = tk.BooleanVar(value=False)
        self.continue_on_error = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="未连接")

        self._set_icon()
        self._load_saved_credentials()
        self._build()
        self._style_treeviews()
        self._refresh_project_list()

    def _set_icon(self) -> None:
        icon = bundled_root() / "assets" / "icon_256.png"
        if not icon.is_file():
            icon = bundled_root() / "assets" / "icon.png"
        if not icon.is_file():
            return
        try:
            photo = tk.PhotoImage(file=str(icon))
            self.root.iconphoto(True, photo)
            self._icon_image = photo
        except tk.TclError:
            return

    def _load_saved_credentials(self) -> None:
        load_env_file(PROJECT_DIR / ".env")
        load_env_file(PROJECT_DIR / "credentials.env")
        self.issuer.set(os.environ.get("ASC_ISSUER_ID", ""))
        self.key_id.set(os.environ.get("ASC_KEY_ID", ""))
        discovered = discover_p8(PROJECT_DIR)
        env_p8 = os.environ.get("ASC_KEY_P8_PATH") or os.environ.get("ASC_PRIVATE_KEY_PATH") or ""
        if env_p8:
            self.p8_path.set(env_p8)
        elif discovered is not None:
            self.p8_path.set(str(discovered))
            if not self.key_id.get():
                self.key_id.set(key_id_from_p8_name(discovered) or "")

    def _build(self) -> None:
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self.root, width=280, fg_color=SIDEBAR, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(6, weight=1)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 8))
        ctk.CTkLabel(brand, text="ASC SKU", font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(brand, text="订阅商品批量工具", text_color=MUTED, font=ctk.CTkFont(size=13)).pack(anchor="w")

        status = ctk.CTkFrame(sidebar, fg_color=CARD, corner_radius=12)
        status.grid(row=1, column=0, sticky="ew", padx=16, pady=(8, 10))
        ctk.CTkLabel(status, textvariable=self.status, font=ctk.CTkFont(size=13)).pack(anchor="w", padx=12, pady=(10, 6))
        ctk.CTkButton(
            status,
            text="连接 App Store Connect",
            height=34,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self._connect,
        ).pack(fill="x", padx=12, pady=(0, 12))

        cred = ctk.CTkFrame(sidebar, fg_color=CARD, corner_radius=12)
        cred.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        ctk.CTkLabel(cred, text="凭证", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            cred,
            text="在 App Store Connect → 用户和访问 → 集成 → App Store Connect API 中查看",
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
            wraplength=236,
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=12, pady=(0, 8))
        ctk.CTkLabel(cred, text="Issuer ID", font=ctk.CTkFont(size=12), anchor="w").pack(anchor="w", padx=12)
        ctk.CTkEntry(
            cred,
            textvariable=self.issuer,
            placeholder_text="发行方 ID，例如 57246542-96fe-1a63-e053-0824d011072a",
            height=30,
        ).pack(fill="x", padx=12, pady=(2, 8))
        ctk.CTkLabel(cred, text="Key ID", font=ctk.CTkFont(size=12), anchor="w").pack(anchor="w", padx=12)
        ctk.CTkEntry(
            cred,
            textvariable=self.key_id,
            placeholder_text="密钥 ID，10 位，例如 AB12CD34EF",
            height=30,
        ).pack(fill="x", padx=12, pady=(2, 8))
        ctk.CTkLabel(cred, text="API 私钥（.p8）", font=ctk.CTkFont(size=12), anchor="w").pack(anchor="w", padx=12)
        p8_row = ctk.CTkFrame(cred, fg_color="transparent")
        p8_row.pack(fill="x", padx=12, pady=(2, 12))
        ctk.CTkEntry(
            p8_row,
            textvariable=self.p8_path,
            placeholder_text="选择下载的 AuthKey_XXXXXXXXXX.p8",
            height=30,
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(p8_row, text="选择", width=48, height=30, fg_color="#3A3A3C", hover_color="#48484A", command=self._browse_p8).pack(
            side="right"
        )

        ctk.CTkLabel(sidebar, text="项目", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=3, column=0, sticky="w", padx=22, pady=(4, 4)
        )
        actions = ctk.CTkFrame(sidebar, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 6))
        ctk.CTkButton(actions, text="新建", width=70, height=30, fg_color="#3A3A3C", hover_color="#48484A", command=self._new_project).pack(
            side="left"
        )
        ctk.CTkButton(actions, text="打开", width=70, height=30, fg_color="#3A3A3C", hover_color="#48484A", command=self._open_project).pack(
            side="left", padx=6
        )
        ctk.CTkButton(actions, text="保存", width=70, height=30, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._save_project).pack(
            side="left"
        )

        self.project_list = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        self.project_list.grid(row=6, column=0, sticky="nsew", padx=10, pady=(0, 8))
        ctk.CTkButton(
            sidebar,
            text="打开数据文件夹",
            height=30,
            fg_color="#3A3A3C",
            hover_color="#48484A",
            command=self._open_data_dir,
        ).grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 16))

        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=18, pady=16)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(
            header,
            textvariable=self.project_name,
            placeholder_text="项目名称",
            height=40,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 12))
        ctk.CTkButton(header, text="预览", width=88, height=36, fg_color="#3A3A3C", hover_color="#48484A", command=lambda: self._run(True)).grid(
            row=0, column=1, padx=(0, 8)
        )
        ctk.CTkButton(
            header,
            text="发布到 ASC",
            width=120,
            height=36,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=lambda: self._run(False),
        ).grid(row=0, column=2)

        tabs = ctk.CTkTabview(main, fg_color=CARD, segmented_button_selected_color=ACCENT)
        tabs.grid(row=1, column=0, sticky="nsew")
        settings = tabs.add("项目设置")
        sku_tab = tabs.add("SKU")
        log_tab = tabs.add("日志")
        settings.grid_columnconfigure(1, weight=1)
        settings.grid_columnconfigure(3, weight=1)
        settings.grid_rowconfigure(6, weight=1)
        sku_tab.grid_rowconfigure(1, weight=1)
        sku_tab.grid_columnconfigure(0, weight=1)
        log_tab.grid_rowconfigure(0, weight=1)
        log_tab.grid_columnconfigure(0, weight=1)

        self._labeled(settings, "App", 0)
        self.app_box = ctk.CTkComboBox(
            settings,
            variable=self.app_choice,
            values=["连接后选择 App"],
            command=lambda _value: self._on_app_selected(),
            height=32,
        )
        self.app_box.grid(row=0, column=1, columnspan=3, sticky="ew", pady=6)
        self._labeled(settings, "订阅组", 1)
        self.group_box = ctk.CTkComboBox(
            settings,
            variable=self.group_choice,
            values=["先选择 App"],
            command=lambda _value: self._on_group_selected(),
            height=32,
        )
        self.group_box.grid(row=1, column=1, sticky="ew", pady=6, padx=(0, 8))
        ctk.CTkEntry(settings, textvariable=self.group_id, placeholder_text="订阅组 ID", height=32).grid(
            row=1, column=2, columnspan=2, sticky="ew", pady=6
        )
        self._labeled(settings, "价格范围", 2)
        ctk.CTkComboBox(
            settings,
            variable=self.price_scope,
            values=choice_labels(PRICE_SCOPE_CHOICES),
            state="readonly",
            width=140,
            height=32,
        ).grid(row=2, column=1, sticky="w", pady=6)
        ctk.CTkLabel(settings, text="基准店面").grid(row=2, column=2, sticky="e", padx=(12, 8))
        ctk.CTkEntry(settings, textvariable=self.base_territory, width=90, height=32).grid(row=2, column=3, sticky="w", pady=6)
        flags = ctk.CTkFrame(settings, fg_color="transparent")
        flags.grid(row=3, column=1, columnspan=3, sticky="w", pady=(4, 6))
        ctk.CTkCheckBox(flags, text="家庭共享", variable=self.family_sharable).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(flags, text="全店面上架", variable=self.available_in_all).pack(side="left")
        publish = ctk.CTkFrame(settings, fg_color="transparent")
        publish.grid(row=4, column=1, columnspan=3, sticky="w", pady=(0, 10))
        ctk.CTkCheckBox(publish, text="补齐已存在 SKU", variable=self.fill_missing).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(publish, text="就近价格点", variable=self.nearest_price).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(publish, text="遇错继续", variable=self.continue_on_error).pack(side="left")

        loc_bar = ctk.CTkFrame(settings, fg_color="transparent")
        loc_bar.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(8, 4))
        ctk.CTkLabel(loc_bar, text="默认本地化", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkButton(loc_bar, text="新增", width=64, height=28, command=self._add_loc).pack(side="left", padx=(10, 4))
        ctk.CTkButton(loc_bar, text="编辑", width=64, height=28, fg_color="#3A3A3C", hover_color="#48484A", command=self._edit_loc).pack(
            side="left", padx=4
        )
        ctk.CTkButton(loc_bar, text="删除", width=64, height=28, fg_color=DANGER, hover_color="#FF6961", command=self._delete_loc).pack(
            side="left", padx=4
        )
        self.loc_tree = ttk.Treeview(settings, columns=("locale", "name", "description"), show="headings")
        loc_headings = {"locale": "语言", "name": "显示名称", "description": "描述"}
        loc_widths = {"locale": 180, "name": 180, "description": 360}
        for key, title in loc_headings.items():
            self.loc_tree.heading(key, text=title, anchor="w")
            self.loc_tree.column(key, width=loc_widths[key], anchor="w", stretch=True, minwidth=80)
        self.loc_tree.grid(row=6, column=0, columnspan=4, sticky="nsew", pady=(0, 8))
        self.loc_tree.bind("<Double-1>", lambda _event: self._edit_loc())

        sku_bar = ctk.CTkFrame(sku_tab, fg_color="transparent")
        sku_bar.grid(row=0, column=0, sticky="ew", pady=(8, 8))
        for text, command in (
            ("新增", self._add_sku),
            ("编辑", self._edit_sku),
            ("删除", self._delete_sku),
            ("生成矩阵", self._generate_matrix),
            ("从 ASC 同步", self._sync_skus),
            ("导入", self._import_skus),
            ("导出", self._export_skus),
            ("下载模板", self._download_sku_template),
        ):
            color = DANGER if text == "删除" else ACCENT if text in {"新增", "生成矩阵", "导入"} else "#3A3A3C"
            hover = "#FF6961" if text == "删除" else ACCENT_HOVER if text in {"新增", "生成矩阵", "导入"} else "#48484A"
            ctk.CTkButton(sku_bar, text=text, width=86, height=30, fg_color=color, hover_color=hover, command=command).pack(
                side="left", padx=(0, 6)
            )
        columns = ("group_level", "reference_name", "product_id", "period", "usd_price", "intro", "state")
        self.tree = ttk.Treeview(sku_tab, columns=columns, show="headings")
        headings = {
            "group_level": "级别",
            "reference_name": "参考名称",
            "product_id": "产品 ID",
            "period": "持续时间",
            "usd_price": "美区价格",
            "intro": "推介促销优惠",
            "state": "状态",
        }
        widths = {
            "group_level": 56,
            "reference_name": 220,
            "product_id": 150,
            "period": 88,
            "usd_price": 88,
            "intro": 220,
            "state": 120,
        }
        for key in columns:
            self.tree.heading(key, text=headings[key], anchor="w")
            self.tree.column(key, width=widths[key], anchor="w", stretch=True, minwidth=48)
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", lambda _event: self._edit_sku())

        log_font = "Consolas" if sys.platform == "win32" else "Menlo"
        self.log = ctk.CTkTextbox(log_tab, font=ctk.CTkFont(family=log_font, size=12))
        self.log.grid(row=0, column=0, sticky="nsew")

    def _labeled(self, parent: ctk.CTkFrame, text: str, row: int) -> None:
        ctk.CTkLabel(parent, text=text, width=80, anchor="w").grid(row=row, column=0, sticky="w", pady=6, padx=(8, 10))

    def _style_treeviews(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        ui_font = "Segoe UI" if sys.platform == "win32" else "Helvetica Neue"
        style.configure(
            "Treeview",
            background="#171A21",
            foreground="#F5F5F7",
            fieldbackground="#171A21",
            rowheight=30,
            borderwidth=0,
            font=(ui_font, 12),
        )
        style.configure(
            "Treeview.Heading",
            background="#2A2E38",
            foreground="#F5F5F7",
            relief="flat",
            font=(ui_font, 12, "bold"),
            anchor="w",
            padding=(8, 6),
        )
        try:
            style.layout(
                "Treeview.Heading",
                [
                    ("Treeheading.cell", {"sticky": "nswe"}),
                    (
                        "Treeheading.border",
                        {
                            "sticky": "nswe",
                            "children": [
                                (
                                    "Treeheading.padding",
                                    {
                                        "sticky": "nswe",
                                        "children": [
                                            ("Treeheading.image", {"side": "right", "sticky": ""}),
                                            ("Treeheading.text", {"sticky": "w"}),
                                        ],
                                    },
                                )
                            ],
                        },
                    ),
                ],
            )
        except tk.TclError:
            pass
        style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#FFFFFF")])

    def _refresh_project_list(self) -> None:
        for child in self.project_list.winfo_children():
            child.destroy()
        directory = PROJECT_DIR / "projects"
        directory.mkdir(exist_ok=True)
        files = sorted(directory.glob("*.json"))
        if not files:
            ctk.CTkLabel(self.project_list, text="还没有项目", text_color=MUTED).pack(anchor="w", padx=8)
            return
        for path in files:
            selected = self.project_path is not None and path.resolve() == self.project_path.resolve()
            label = "空白模板" if path.name.startswith("_") else path.stem
            ctk.CTkButton(
                self.project_list,
                text=label,
                anchor="w",
                height=34,
                fg_color=ACCENT if selected else "transparent",
                hover_color="#2A2E38",
                command=lambda current=path: self._open_path(current),
            ).pack(fill="x", pady=2, padx=4)

    def _append_log(self, text: str) -> None:
        def write() -> None:
            self.log.insert("end", text)
            self.log.see("end")

        self.root.after(0, write)

    def _set_status(self, text: str) -> None:
        self.root.after(0, lambda: self.status.set(text))

    def _open_data_dir(self) -> None:
        path = data_dir()
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _browse_p8(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 App Store Connect .p8",
            initialdir=str(PROJECT_DIR),
            filetypes=[("Private key", "*.p8"), ("All files", "*.*")],
        )
        if path:
            self.p8_path.set(path)
            key_id = key_id_from_p8_name(Path(path))
            if key_id and not self.key_id.get():
                self.key_id.set(key_id)

    def _connect(self) -> None:
        self._run_background("正在连接…", self._connect_worker)

    def _connect_worker(self) -> None:
        args = Namespace(issuer_id=self.issuer.get().strip(), key_id=self.key_id.get().strip(), p8=self.p8_path.get().strip())
        self.client = ASCClient(load_auth(args))
        p8 = Path(self.p8_path.get().strip()).expanduser()
        if p8.is_file():
            stored = save_credentials(self.issuer.get().strip(), self.key_id.get().strip(), p8)
            self.p8_path.set(str(stored))
        self.apps = fetch_apps(self.client)
        app_labels = [f"{app['name']}  ({app['bundle']})" for app in self.apps]
        selected_app_index = -1
        for index, app in enumerate(self.apps):
            if (self.saved_app_id and app["id"] == self.saved_app_id) or (
                self.saved_bundle_id and app["bundle"] == self.saved_bundle_id
            ):
                selected_app_index = index
                self.groups = fetch_groups(self.client, app["id"])
                break
        else:
            self.groups = []
        group_labels = [f"{group['name']}  ({group['id']})" for group in self.groups]
        selected_group_index = -1
        group_id = self.group_id.get().strip()
        if group_id:
            for index, group in enumerate(self.groups):
                if group["id"] == group_id:
                    selected_group_index = index
                    break

        def apply() -> None:
            self.app_box.configure(values=app_labels or ["未找到 App"])
            if selected_app_index >= 0:
                self.app_choice.set(app_labels[selected_app_index])
            self.group_box.configure(values=group_labels or ["未找到订阅组"])
            if selected_group_index >= 0:
                self.group_choice.set(group_labels[selected_group_index])

        self.root.after(0, apply)
        self._set_status(f"已连接 · {len(self.apps)} 个 App")
        self._append_log(f"连接成功，共 {len(self.apps)} 个 App。\n")

    def _selected_app(self) -> dict[str, str] | None:
        label = self.app_choice.get().strip()
        for app in self.apps:
            if f"{app['name']}  ({app['bundle']})" == label:
                return app
        return None

    def _on_app_selected(self) -> None:
        app = self._selected_app()
        if app is None or self.client is None:
            return
        self._run_background("正在加载订阅组…", lambda: self._load_groups_worker(app["id"]))

    def _load_groups_worker(self, app_id: str) -> None:
        assert self.client is not None
        self.groups = fetch_groups(self.client, app_id)
        labels = [f"{group['name']}  ({group['id']})" for group in self.groups]

        def apply() -> None:
            self.group_box.configure(values=labels or ["未找到订阅组"])
            self._restore_group_selection()

        self.root.after(0, apply)
        self._append_log(f"App {app_id} 有 {len(self.groups)} 个订阅组。\n")

    def _restore_app_selection(self) -> None:
        target_id = self.saved_app_id
        target_bundle = self.saved_bundle_id
        if not target_id and not target_bundle:
            return
        for app in self.apps:
            if (target_id and app["id"] == target_id) or (target_bundle and app["bundle"] == target_bundle):
                self.app_choice.set(f"{app['name']}  ({app['bundle']})")
                self._on_app_selected()
                return

    def _restore_group_selection(self) -> None:
        group_id = self.group_id.get().strip()
        if not group_id:
            return
        for group in self.groups:
            if group["id"] == group_id:
                self.group_choice.set(f"{group['name']}  ({group['id']})")
                return

    def _on_group_selected(self) -> None:
        label = self.group_choice.get()
        for group in self.groups:
            if f"{group['name']}  ({group['id']})" == label:
                self.group_id.set(group["id"])
                return

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for sku in self.skus:
            self.tree.insert(
                "",
                "end",
                values=(
                    sku.get("group_level", ""),
                    sku.get("reference_name", ""),
                    sku.get("product_id", ""),
                    choice_label(PERIOD_CHOICES, str(sku.get("period", ""))),
                    sku.get("usd_price", ""),
                    format_intro_text(sku.get("intro"), str(sku.get("period", ""))),
                    choice_label(STATE_CHOICES, str(sku.get("state", "")), str(sku.get("state", "") or "")),
                ),
            )

    def _refresh_loc_tree(self) -> None:
        self.loc_tree.delete(*self.loc_tree.get_children())
        for item in self.localizations:
            self.loc_tree.insert(
                "",
                "end",
                values=(
                    choice_label(LOCALE_CHOICES, str(item.get("locale", "")), str(item.get("locale", ""))),
                    item.get("name", ""),
                    item.get("description", ""),
                ),
            )

    def _selected_loc_index(self) -> int | None:
        selected = self.loc_tree.selection()
        if not selected:
            return None
        return self.loc_tree.index(selected[0])

    def _add_loc(self) -> None:
        dialog = LocalizationDialog(self.root)
        self.root.wait_window(dialog)
        if dialog.result:
            self.localizations.append(dialog.result)
            self._refresh_loc_tree()

    def _edit_loc(self) -> None:
        index = self._selected_loc_index()
        if index is None:
            return
        dialog = LocalizationDialog(self.root, self.localizations[index])
        self.root.wait_window(dialog)
        if dialog.result:
            self.localizations[index] = dialog.result
            self._refresh_loc_tree()

    def _delete_loc(self) -> None:
        index = self._selected_loc_index()
        if index is None:
            return
        item = self.localizations[index]
        label = choice_label(LOCALE_CHOICES, str(item.get("locale", "")), str(item.get("locale", "") or "这条本地化"))
        if not confirm_delete(self.root, "删除本地化", f"「{label}」"):
            return
        del self.localizations[index]
        self._refresh_loc_tree()

    def _generate_matrix(self) -> None:
        if not self.localizations:
            messagebox.showerror("生成矩阵", "请先添加至少一条默认本地化。")
            return
        dialog = MatrixDialog(self.root)
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        first = self.localizations[0]
        extra = self.localizations[1:]
        try:
            catalog = scaffold_catalog(
                group_id=self.group_id.get().strip() or "pending",
                prefix=dialog.result["prefix"],
                name_prefix=dialog.result["name_prefix"],
                period=dialog.result["period"],
                version=dialog.result["version"],
                usd_price=dialog.result["usd_price"],
                intro_usd=dialog.result["intro_usd"],
                start_level=next_group_level(self.skus),
                display_name=first["name"],
                display_description=first.get("description", ""),
                locale=first["locale"],
                extra_localizations=extra or None,
            )
        except ASCError as error:
            messagebox.showerror("生成矩阵", str(error))
            return
        existing = {sku.get("product_id") for sku in self.skus}
        added = 0
        for sku in catalog["subscriptions"]:
            if sku["product_id"] in existing:
                continue
            self.skus.append(sku)
            added += 1
        self._refresh_tree()
        self._append_log(f"矩阵生成完成，新增 {added} 个 SKU。\n")

    def _selected_sku_index(self) -> int | None:
        selected = self.tree.selection()
        if not selected:
            return None
        return self.tree.index(selected[0])

    def _add_sku(self) -> None:
        dialog = SKUDialog(self.root, next_level=next_group_level(self.skus))
        self.root.wait_window(dialog)
        if dialog.result:
            self.skus.append(dialog.result)
            self._refresh_tree()

    def _edit_sku(self) -> None:
        index = self._selected_sku_index()
        if index is None:
            return
        dialog = SKUDialog(self.root, self.skus[index], next_level=next_group_level(self.skus))
        self.root.wait_window(dialog)
        if dialog.result:
            updated = dict(self.skus[index])
            updated.update(dialog.result)
            if "review_note" not in dialog.result:
                updated.pop("review_note", None)
            if "review_screenshot" not in dialog.result:
                updated.pop("review_screenshot", None)
            if "intro" not in dialog.result:
                updated.pop("intro", None)
            self.skus[index] = updated
            self._refresh_tree()

    def _delete_sku(self) -> None:
        index = self._selected_sku_index()
        if index is None:
            return
        sku = self.skus[index]
        label = sku.get("product_id") or sku.get("reference_name") or "这个 SKU"
        if not confirm_delete(self.root, "删除 SKU", f"「{label}」"):
            return
        del self.skus[index]
        self._refresh_tree()

    def _choose_exchange_path(self, *, title: str, suffix: str, initialfile: str) -> Path | None:
        filetypes = [("JSON", "*.json")] if suffix == ".json" else [("Excel", "*.xlsx")]
        chosen = filedialog.asksaveasfilename(
            title=title,
            defaultextension=suffix,
            initialfile=initialfile,
            filetypes=filetypes,
        )
        if not chosen:
            return None
        path = Path(chosen)
        if path.suffix.lower() != suffix:
            path = path.with_suffix(suffix)
        return path

    def _hydrate_imported_screenshots(self, skus: list[dict[str, Any]]) -> list[dict[str, Any]]:
        hydrated: list[dict[str, Any]] = []
        for sku in skus:
            shot = str(sku.get("review_screenshot") or "").strip()
            if not shot:
                hydrated.append(sku)
                continue
            source = Path(shot).expanduser()
            if not source.is_file():
                hydrated.append(sku)
                continue
            copied = dict(sku)
            try:
                copied["review_screenshot"] = store_review_screenshot(str(sku.get("product_id", "")), str(source))
            except ASCError:
                pass
            hydrated.append(copied)
        return hydrated

    def _import_skus(self) -> None:
        chosen = filedialog.askopenfilename(
            title="导入 SKU",
            filetypes=[
                ("SKU 文件", "*.json *.xlsx"),
                ("JSON", "*.json"),
                ("Excel", "*.xlsx"),
            ],
        )
        if not chosen:
            return
        path = Path(chosen)
        try:
            incoming = self._hydrate_imported_screenshots(load_skus(path))
        except ASCError as error:
            messagebox.showerror("导入失败", str(error))
            return
        if not incoming:
            messagebox.showinfo("导入", "文件里没有 SKU。")
            return
        replace = False
        if self.skus:
            answer = messagebox.askyesnocancel(
                "导入 SKU",
                f"将导入 {len(incoming)} 个 SKU。\n\n"
                "是：按产品 ID 合并（已有的覆盖，新的追加）\n"
                "否：清空当前列表后全部替换\n"
                "取消：不导入",
                parent=self.root,
            )
            if answer is None:
                return
            replace = not answer
        merged, added, updated = merge_skus(self.skus, incoming, replace=replace)
        self.skus = merged
        self._refresh_tree()
        if replace:
            self._append_log(f"已从 {path.name} 替换导入 {len(merged)} 个 SKU。检查列表后即可发布到 ASC。\n")
        else:
            self._append_log(
                f"已从 {path.name} 导入 SKU：新增 {added}，覆盖 {updated}。检查列表后即可发布到 ASC。\n"
            )

    def _export_skus(self) -> None:
        if not self.skus:
            messagebox.showinfo("导出", "当前没有 SKU 可导出。")
            return
        dialog = ActionDialog(
            self.root,
            "导出 SKU",
            "导出格式与导入相同，可再导入后发布。从 ASC 同步下来的 SKU 也会一并导出。",
            (("导出 JSON", "json"), ("导出 Excel", "excel")),
        )
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        kind = dialog.result["action"]
        suffix = ".json" if kind == "json" else ".xlsx"
        path = self._choose_exchange_path(
            title="导出 SKU",
            suffix=suffix,
            initialfile=f"skus{suffix}",
        )
        if path is None:
            return
        try:
            dump_skus(self.skus, path)
        except (ASCError, OSError) as error:
            messagebox.showerror("导出失败", str(error))
            return
        self._append_log(f"已导出 {len(self.skus)} 个 SKU 到 {path}\n")

    def _download_sku_template(self) -> None:
        dialog = ActionDialog(
            self.root,
            "下载导入模板",
            "模板已含示例数据。改成你的产品 ID、价格和推介优惠后，点「导入」，再点「发布到 ASC」。",
            (("JSON 模板", "json"), ("Excel 模板", "excel")),
        )
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        kind = dialog.result["action"]
        suffix = ".json" if kind == "json" else ".xlsx"
        path = self._choose_exchange_path(
            title="保存导入模板",
            suffix=suffix,
            initialfile=f"sku-import-template{suffix}",
        )
        if path is None:
            return
        try:
            if kind == "json":
                write_json_template(path)
            else:
                write_excel_template(path)
        except (ASCError, OSError) as error:
            messagebox.showerror("模板", str(error))
            return
        self._append_log(f"已保存导入模板：{path}\n")

    def _sync_skus(self) -> None:
        if self.client is None or not self.group_id.get().strip():
            messagebox.showerror("同步", "请先连接 ASC 并选择订阅组。")
            return
        self._run_background("正在同步 SKU…", self._sync_skus_worker)

    def _sync_skus_worker(self) -> None:
        assert self.client is not None
        rows = fetch_skus(self.client, self.group_id.get().strip(), include_pricing=True)
        local_by_id = {str(sku.get("product_id", "")): sku for sku in self.skus if sku.get("product_id")}
        merged: list[dict[str, Any]] = []
        added = 0
        updated = 0
        priced = 0
        offered = 0
        for row in rows:
            product_id = row["product"]
            pricing = row.get("pricing") if isinstance(row.get("pricing"), dict) else None
            if pricing and pricing.get("usd_price"):
                priced += 1
            if pricing and pricing.get("intro"):
                offered += 1
            if product_id in local_by_id:
                merged.append(merge_local_sku_with_asc(local_by_id.pop(product_id), row))
                updated += 1
            else:
                merged.append(sku_dict_from_asc_row(row))
                added += 1
        merged.extend(sku for sku in local_by_id.values())
        merged.sort(key=lambda sku: int(sku.get("group_level") or 10**9))

        def apply() -> None:
            self.skus = merged
            self._refresh_tree()

        self.root.after(0, apply)
        self._append_log(
            f"从 ASC 同步到 {len(rows)} 个 SKU，更新 {updated} 行，新增 {added} 行"
            f"（美区价格 {priced} 个，推介优惠 {offered} 个）。\n"
        )

    def _new_project(self) -> None:
        self.project_path = None
        self.project_name.set("")
        self.app_choice.set("")
        self.group_choice.set("")
        self.group_id.set("")
        self.family_sharable.set(False)
        self.available_in_all.set(True)
        self.saved_app_id = ""
        self.saved_bundle_id = ""
        self.localizations = []
        self.skus = []
        self._refresh_loc_tree()
        self._refresh_tree()
        self._refresh_project_list()
        self._append_log("已新建空白项目。\n")

    def _open_path(self, path: Path) -> None:
        catalog = load_catalog(path, strict=False)
        self._apply_catalog(catalog)
        self.project_path = path
        self._refresh_project_list()
        self._append_log(f"已打开 {path}\n")

    def _open_project(self) -> None:
        path = filedialog.askopenfilename(
            title="打开项目 JSON",
            initialdir=str(PROJECT_DIR / "projects"),
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            self._open_path(Path(path))

    def _apply_catalog(self, catalog: Catalog) -> None:
        self.project_name.set(catalog.name or "")
        self.group_id.set(catalog.group_id)
        self.base_territory.set(catalog.base_territory)
        self.price_scope.set(choice_label(PRICE_SCOPE_CHOICES, catalog.price_scope, "所有店面"))
        self.family_sharable.set(catalog.family_sharable)
        self.available_in_all.set(catalog.available_in_all_territories)
        self.saved_app_id = catalog.app_id or ""
        self.saved_bundle_id = catalog.bundle_id or ""
        self.localizations = [
            {"locale": item.locale, "name": item.name, "description": item.description}
            for item in catalog.default_localizations
        ]
        self._refresh_loc_tree()
        if catalog.app_id or catalog.bundle_id:
            self._restore_app_selection()
        payload = catalog_to_dict(catalog)
        self.skus = list(payload.get("subscriptions") or [])
        self._refresh_tree()

    def _catalog_from_form(self, *, strict: bool) -> Catalog:
        app = self._selected_app()
        payload = {
            "name": self.project_name.get().strip(),
            "app_id": app["id"] if app else self.saved_app_id,
            "bundle_id": app["bundle"] if app else self.saved_bundle_id,
            "group_id": self.group_id.get().strip(),
            "base_territory": self.base_territory.get().strip() or "USA",
            "price_scope": choice_value(PRICE_SCOPE_CHOICES, self.price_scope.get(), "all"),
            "family_sharable": self.family_sharable.get(),
            "available_in_all_territories": self.available_in_all.get(),
            "default_localizations": self.localizations,
            "subscriptions": self.skus,
        }
        return catalog_from_dict(payload, strict=strict)

    def _save_project(self) -> None:
        try:
            catalog = self._catalog_from_form(strict=False)
        except ASCError as error:
            messagebox.showerror("保存失败", str(error))
            return
        path = self.project_path
        if path is None:
            projects = PROJECT_DIR / "projects"
            projects.mkdir(exist_ok=True)
            chosen = filedialog.asksaveasfilename(
                title="保存项目 JSON",
                initialdir=str(projects),
                defaultextension=".json",
                filetypes=[("JSON", "*.json")],
            )
            if not chosen:
                return
            self.project_path = Path(chosen)
        save_catalog(self.project_path, catalog)
        self._refresh_project_list()
        self._append_log(f"已保存 {self.project_path}\n")

    def _run(self, dry_run: bool) -> None:
        if self.client is None:
            messagebox.showerror("运行", "请先连接 ASC。")
            return
        try:
            catalog = self._catalog_from_form(strict=True)
        except ASCError as error:
            messagebox.showerror("配置不完整", str(error))
            return
        if not dry_run and not messagebox.askyesno("发布到 ASC", "将向 App Store Connect 写入订阅商品，确认继续？"):
            return
        options = CreateOptions(
            dry_run=dry_run,
            fill_missing=self.fill_missing.get(),
            nearest_price=self.nearest_price.get(),
            continue_on_error=self.continue_on_error.get(),
        )
        title = "预览" if dry_run else "发布"
        self._run_background(f"{title}中…", lambda: self._create_worker(catalog, options))

    def _create_worker(self, catalog: Catalog, options: CreateOptions) -> None:
        assert self.client is not None
        stdout = sys.stdout
        sys.stdout = TextRedirect(self._append_log)  # type: ignore[assignment]
        try:
            code = create_from_catalog(self.client, catalog, options)
            self._append_log(f"\n完成，退出码 {code}\n")
        finally:
            sys.stdout = stdout

    def _run_background(self, status: str, worker: Callable[[], None]) -> None:
        if self.busy:
            return
        self.busy = True
        self._set_status(status)

        def run() -> None:
            try:
                worker()
            except ASCError as error:
                self._append_log(f"错误：{format_errors(error)}\n")
                self.root.after(0, lambda: messagebox.showerror("ASC", format_errors(error)))
            except Exception as error:  # noqa: BLE001
                self._append_log(f"错误：{error}\n")
                self.root.after(0, lambda: messagebox.showerror("错误", str(error)))
            finally:
                self.busy = False
                self._set_status("已连接 · 就绪" if self.client else "未连接")

        threading.Thread(target=run, daemon=True).start()


def run_gui() -> int:
    os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")
    if sys.platform == "win32":
        try:
            from ctypes import windll

            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    seed_user_data()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_gui())
