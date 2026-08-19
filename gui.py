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

from create_subscriptions import (
    ASCClient,
    ASCError,
    Catalog,
    CreateOptions,
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
    save_catalog,
    save_credentials,
    scaffold_catalog,
    seed_user_data,
)

PERIODS = ("ONE_WEEK", "ONE_MONTH", "TWO_MONTHS", "THREE_MONTHS", "SIX_MONTHS", "ONE_YEAR")
INTRO_MODES = ("", "FREE_TRIAL", "PAY_AS_YOU_GO", "PAY_UP_FRONT")
INTRO_DURATIONS = (
    "THREE_DAYS",
    "ONE_WEEK",
    "TWO_WEEKS",
    "ONE_MONTH",
    "TWO_MONTHS",
    "THREE_MONTHS",
    "SIX_MONTHS",
    "ONE_YEAR",
)
COMMON_LOCALES = (
    "en-US",
    "zh-Hans",
    "zh-Hant",
    "ja",
    "ko",
    "es-MX",
    "pt-BR",
    "fr-FR",
    "de-DE",
    "ar-SA",
)

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

    def _row(self, parent: ctk.CTkFrame, row: int, label: str, widget: ctk.CTkBaseClass) -> None:
        ctk.CTkLabel(parent, text=label, width=96, anchor="w").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 12))
        widget.grid(row=row, column=1, sticky="ew", pady=6)


class SKUDialog(FormDialog):
    def __init__(self, master: tk.Misc, sku: dict[str, Any] | None = None) -> None:
        super().__init__(master, "SKU", "460x520")
        sku = sku or {}
        intro = sku.get("intro") or {}
        self.vars = {
            "product_id": tk.StringVar(value=str(sku.get("product_id", ""))),
            "reference_name": tk.StringVar(value=str(sku.get("reference_name", ""))),
            "period": tk.StringVar(value=str(sku.get("period", "ONE_MONTH"))),
            "usd_price": tk.StringVar(value=str(sku.get("usd_price", ""))),
            "group_level": tk.StringVar(value="" if sku.get("group_level") is None else str(sku.get("group_level"))),
            "intro_mode": tk.StringVar(value=str(intro.get("mode", ""))),
            "intro_duration": tk.StringVar(value=str(intro.get("duration", "THREE_DAYS"))),
            "intro_periods": tk.StringVar(value=str(intro.get("number_of_periods", 1))),
            "intro_usd": tk.StringVar(value=str(intro.get("usd_price", ""))),
        }
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=16)
        body.grid_columnconfigure(1, weight=1)
        rows = [
            ("产品 ID", "product_id", None),
            ("参考名称", "reference_name", None),
            ("周期", "period", PERIODS),
            ("美区价格", "usd_price", None),
            ("级别", "group_level", None),
            ("推介类型", "intro_mode", INTRO_MODES),
            ("推介时长", "intro_duration", INTRO_DURATIONS),
            ("推介期数", "intro_periods", None),
            ("推介价格", "intro_usd", None),
        ]
        for index, (label, key, values) in enumerate(rows):
            if values is None:
                widget: ctk.CTkBaseClass = ctk.CTkEntry(body, textvariable=self.vars[key], height=32)
            else:
                widget = ctk.CTkComboBox(body, variable=self.vars[key], values=list(values), state="readonly", height=32)
            self._row(body, index, label, widget)
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.grid(row=len(rows), column=0, columnspan=2, sticky="e", pady=(16, 0))
        ctk.CTkButton(buttons, text="取消", fg_color="#3A3A3C", hover_color="#48484A", width=88, command=self.destroy).pack(
            side="right", padx=(8, 0)
        )
        ctk.CTkButton(buttons, text="确定", width=88, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._confirm).pack(
            side="right"
        )

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
            "period": self.vars["period"].get(),
            "usd_price": usd_price,
        }
        level = self.vars["group_level"].get().strip()
        if level:
            payload["group_level"] = int(level)
        mode = self.vars["intro_mode"].get().strip()
        if mode:
            intro: dict[str, Any] = {
                "mode": mode,
                "duration": self.vars["intro_duration"].get(),
                "number_of_periods": int(self.vars["intro_periods"].get() or 1),
            }
            intro_usd = self.vars["intro_usd"].get().strip()
            if intro_usd:
                intro["usd_price"] = intro_usd
            payload["intro"] = intro
        self.result = payload
        self.destroy()


class LocalizationDialog(FormDialog):
    def __init__(self, master: tk.Misc, item: dict[str, str] | None = None) -> None:
        super().__init__(master, "本地化", "420x240")
        item = item or {}
        self.locale = tk.StringVar(value=str(item.get("locale", "en-US")))
        self.name = tk.StringVar(value=str(item.get("name", "")))
        self.description = tk.StringVar(value=str(item.get("description", "")))
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=16)
        body.grid_columnconfigure(1, weight=1)
        self._row(body, 0, "语言", ctk.CTkComboBox(body, variable=self.locale, values=list(COMMON_LOCALES), height=32))
        self._row(body, 1, "显示名称", ctk.CTkEntry(body, textvariable=self.name, height=32))
        self._row(body, 2, "描述", ctk.CTkEntry(body, textvariable=self.description, height=32))
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ctk.CTkButton(buttons, text="取消", fg_color="#3A3A3C", hover_color="#48484A", width=88, command=self.destroy).pack(
            side="right", padx=(8, 0)
        )
        ctk.CTkButton(buttons, text="确定", width=88, fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._confirm).pack(
            side="right"
        )

    def _confirm(self) -> None:
        locale = self.locale.get().strip()
        name = self.name.get().strip()
        if not locale or not name:
            messagebox.showerror("本地化", "语言和显示名称不能为空。", parent=self)
            return
        self.result = {"locale": locale, "name": name, "description": self.description.get().strip()}
        self.destroy()


class MatrixDialog(FormDialog):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, "生成 SKU 矩阵", "460x460")
        self.vars = {
            "prefix": tk.StringVar(),
            "name_prefix": tk.StringVar(),
            "period": tk.StringVar(value="ONE_MONTH"),
            "version": tk.StringVar(value="1"),
            "usd_price": tk.StringVar(),
            "intro_usd": tk.StringVar(),
            "start_level": tk.StringVar(value="1"),
        }
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=16)
        body.grid_columnconfigure(1, weight=1)
        rows = [
            ("产品 ID 前缀", "prefix", None),
            ("参考名前缀", "name_prefix", None),
            ("周期", "period", PERIODS),
            ("版本号", "version", None),
            ("美区价格", "usd_price", None),
            ("付费推介价", "intro_usd", None),
            ("起始级别", "start_level", None),
        ]
        for index, (label, key, values) in enumerate(rows):
            if values is None:
                widget: ctk.CTkBaseClass = ctk.CTkEntry(body, textvariable=self.vars[key], height=32)
            else:
                widget = ctk.CTkComboBox(body, variable=self.vars[key], values=list(values), state="readonly", height=32)
            self._row(body, index, label, widget)
        ctk.CTkLabel(
            body,
            text="默认生成 4 档：无试用 / 前三天免费 / 付费推介 / 首周免费。已存在的产品 ID 会跳过。",
            text_color=MUTED,
            wraplength=380,
            justify="left",
        ).grid(row=len(rows), column=0, columnspan=2, sticky="w", pady=(8, 0))
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="e", pady=(16, 0))
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
            messagebox.showerror("生成矩阵", "默认矩阵包含付费推介档，请填写付费推介价。", parent=self)
            return
        try:
            version = int(self.vars["version"].get().strip() or 1)
            start_level = int(self.vars["start_level"].get().strip() or 1)
        except ValueError:
            messagebox.showerror("生成矩阵", "版本号和起始级别必须是整数。", parent=self)
            return
        self.result = {
            "prefix": prefix,
            "name_prefix": name_prefix,
            "period": self.vars["period"].get(),
            "version": version,
            "usd_price": usd_price,
            "intro_usd": intro_usd,
            "start_level": start_level,
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
        self.price_scope = tk.StringVar(value="all")
        self.review_note = tk.StringVar()
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
        ctk.CTkLabel(cred, text="凭证", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(10, 4))
        ctk.CTkEntry(cred, textvariable=self.issuer, placeholder_text="Issuer ID", height=30).pack(fill="x", padx=12, pady=3)
        ctk.CTkEntry(cred, textvariable=self.key_id, placeholder_text="Key ID", height=30).pack(fill="x", padx=12, pady=3)
        p8_row = ctk.CTkFrame(cred, fg_color="transparent")
        p8_row.pack(fill="x", padx=12, pady=(3, 12))
        ctk.CTkEntry(p8_row, textvariable=self.p8_path, placeholder_text=".p8 路径", height=30).pack(
            side="left", fill="x", expand=True, padx=(0, 6)
        )
        ctk.CTkButton(p8_row, text="…", width=36, height=30, fg_color="#3A3A3C", hover_color="#48484A", command=self._browse_p8).pack(
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
            text="创建到 ASC",
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
        sku_tab.grid_rowconfigure(1, weight=1)
        sku_tab.grid_columnconfigure(0, weight=1)
        log_tab.grid_rowconfigure(1, weight=1)
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
        ctk.CTkEntry(settings, textvariable=self.group_id, placeholder_text="Group ID", height=32).grid(
            row=1, column=2, columnspan=2, sticky="ew", pady=6
        )
        self._labeled(settings, "价格范围", 2)
        ctk.CTkComboBox(settings, variable=self.price_scope, values=["usa", "all"], state="readonly", width=120, height=32).grid(
            row=2, column=1, sticky="w", pady=6
        )
        ctk.CTkLabel(settings, text="基准店面").grid(row=2, column=2, sticky="e", padx=(12, 8))
        ctk.CTkEntry(settings, textvariable=self.base_territory, width=90, height=32).grid(row=2, column=3, sticky="w", pady=6)
        self._labeled(settings, "审核备注", 3)
        ctk.CTkEntry(settings, textvariable=self.review_note, height=32).grid(row=3, column=1, columnspan=3, sticky="ew", pady=6)
        flags = ctk.CTkFrame(settings, fg_color="transparent")
        flags.grid(row=4, column=1, columnspan=3, sticky="w", pady=(4, 10))
        ctk.CTkCheckBox(flags, text="家庭共享", variable=self.family_sharable).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(flags, text="全店面上架", variable=self.available_in_all).pack(side="left")

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
        self.loc_tree = ttk.Treeview(settings, columns=("locale", "name", "description"), show="headings", height=4)
        self.loc_tree.heading("locale", text="语言")
        self.loc_tree.heading("name", text="显示名称")
        self.loc_tree.heading("description", text="描述")
        self.loc_tree.column("locale", width=100)
        self.loc_tree.column("name", width=180)
        self.loc_tree.column("description", width=360)
        self.loc_tree.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        self.loc_tree.bind("<Double-1>", lambda _event: self._edit_loc())

        sku_bar = ctk.CTkFrame(sku_tab, fg_color="transparent")
        sku_bar.grid(row=0, column=0, sticky="ew", pady=(8, 8))
        for text, command in (
            ("新增", self._add_sku),
            ("编辑", self._edit_sku),
            ("删除", self._delete_sku),
            ("生成矩阵", self._generate_matrix),
            ("从 ASC 同步", self._sync_skus),
        ):
            color = DANGER if text == "删除" else ACCENT if text in {"新增", "生成矩阵"} else "#3A3A3C"
            hover = "#FF6961" if text == "删除" else ACCENT_HOVER if text in {"新增", "生成矩阵"} else "#48484A"
            ctk.CTkButton(sku_bar, text=text, width=92, height=30, fg_color=color, hover_color=hover, command=command).pack(
                side="left", padx=(0, 6)
            )
        columns = ("product_id", "reference_name", "period", "usd_price", "group_level", "intro")
        self.tree = ttk.Treeview(sku_tab, columns=columns, show="headings")
        headings = {
            "product_id": "产品 ID",
            "reference_name": "参考名称",
            "period": "周期",
            "usd_price": "美区价",
            "group_level": "级别",
            "intro": "推介优惠",
        }
        widths = {"product_id": 170, "reference_name": 240, "period": 120, "usd_price": 80, "group_level": 50, "intro": 280}
        for key in columns:
            self.tree.heading(key, text=headings[key])
            self.tree.column(key, width=widths[key], stretch=True)
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", lambda _event: self._edit_sku())

        opts = ctk.CTkFrame(log_tab, fg_color="transparent")
        opts.grid(row=0, column=0, sticky="ew", pady=(8, 8))
        ctk.CTkCheckBox(opts, text="补齐已存在 SKU", variable=self.fill_missing).pack(side="left", padx=(0, 14))
        ctk.CTkCheckBox(opts, text="就近价格点", variable=self.nearest_price).pack(side="left", padx=(0, 14))
        ctk.CTkCheckBox(opts, text="遇错继续", variable=self.continue_on_error).pack(side="left")
        log_font = "Consolas" if sys.platform == "win32" else "Menlo"
        self.log = ctk.CTkTextbox(log_tab, font=ctk.CTkFont(family=log_font, size=12))
        self.log.grid(row=1, column=0, sticky="nsew")

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
        )
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
            intro = sku.get("intro")
            intro_text = ""
            if intro:
                intro_text = f"{intro.get('mode', '')}/{intro.get('duration', '')}"
                if intro.get("usd_price"):
                    intro_text += f"@{intro['usd_price']}"
            self.tree.insert(
                "",
                "end",
                values=(
                    sku.get("product_id", ""),
                    sku.get("reference_name", ""),
                    sku.get("period", ""),
                    sku.get("usd_price", ""),
                    sku.get("group_level", ""),
                    intro_text,
                ),
            )

    def _refresh_loc_tree(self) -> None:
        self.loc_tree.delete(*self.loc_tree.get_children())
        for item in self.localizations:
            self.loc_tree.insert("", "end", values=(item.get("locale", ""), item.get("name", ""), item.get("description", "")))

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
                start_level=dialog.result["start_level"],
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
        dialog = SKUDialog(self.root)
        self.root.wait_window(dialog)
        if dialog.result:
            self.skus.append(dialog.result)
            self._refresh_tree()

    def _edit_sku(self) -> None:
        index = self._selected_sku_index()
        if index is None:
            return
        dialog = SKUDialog(self.root, self.skus[index])
        self.root.wait_window(dialog)
        if dialog.result:
            self.skus[index] = dialog.result
            self._refresh_tree()

    def _delete_sku(self) -> None:
        index = self._selected_sku_index()
        if index is None:
            return
        del self.skus[index]
        self._refresh_tree()

    def _sync_skus(self) -> None:
        if self.client is None or not self.group_id.get().strip():
            messagebox.showerror("同步", "请先连接 ASC 并选择订阅组。")
            return
        self._run_background("正在同步 SKU…", self._sync_skus_worker)

    def _sync_skus_worker(self) -> None:
        assert self.client is not None
        rows = fetch_skus(self.client, self.group_id.get().strip())
        existing = {sku.get("product_id") for sku in self.skus}
        added = 0
        for row in rows:
            product_id = row["product"]
            if product_id in existing:
                continue
            self.skus.append(
                {
                    "product_id": product_id,
                    "reference_name": row["name"],
                    "period": row["period"],
                    "usd_price": "0.99",
                    "group_level": int(row["level"]) if row["level"] else None,
                }
            )
            added += 1
        self.root.after(0, self._refresh_tree)
        self._append_log(f"从 ASC 同步到 {len(rows)} 个 SKU，新增 {added} 行（价格请自行核对）。\n")

    def _new_project(self) -> None:
        self.project_path = None
        self.project_name.set("")
        self.app_choice.set("")
        self.group_choice.set("")
        self.group_id.set("")
        self.review_note.set("")
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
        self.price_scope.set(catalog.price_scope)
        self.review_note.set(catalog.review_note or "")
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
            "price_scope": self.price_scope.get(),
            "family_sharable": self.family_sharable.get(),
            "available_in_all_territories": self.available_in_all.get(),
            "review_note": self.review_note.get().strip(),
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
        if not dry_run and not messagebox.askyesno("创建到 ASC", "将向 App Store Connect 写入订阅商品，确认继续？"):
            return
        options = CreateOptions(
            dry_run=dry_run,
            fill_missing=self.fill_missing.get(),
            nearest_price=self.nearest_price.get(),
            continue_on_error=self.continue_on_error.get(),
        )
        title = "预览" if dry_run else "创建"
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
