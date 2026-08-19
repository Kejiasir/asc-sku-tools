#!/usr/bin/env python3
"""Batch-create App Store Connect auto-renewable subscription SKUs.

Credentials stay in this directory:
  AuthKey_XXXXXXXXXX.p8
  .env  (ASC_ISSUER_ID, optional ASC_KEY_ID)

Project data is a JSON catalog — one file per app. Nothing app-specific is
hardcoded in the engine.

  python3 create_subscriptions.py          # GUI
  python3 create_subscriptions.py gui
  python3 create_subscriptions.py list-apps
  python3 create_subscriptions.py create --config projects/my-app.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import jwt
import requests

ASC_HOST = "https://api.appstoreconnect.apple.com"
TOKEN_LIFETIME_SECONDS = 18 * 60
REQUEST_TIMEOUT_SECONDS = 60

PERIOD_ALIASES = {
    "WEEK": "ONE_WEEK",
    "1WEEK": "ONE_WEEK",
    "P1W": "ONE_WEEK",
    "ONE_WEEK": "ONE_WEEK",
    "MONTH": "ONE_MONTH",
    "1MONTH": "ONE_MONTH",
    "P1M": "ONE_MONTH",
    "ONE_MONTH": "ONE_MONTH",
    "TWO_MONTHS": "TWO_MONTHS",
    "P2M": "TWO_MONTHS",
    "THREE_MONTHS": "THREE_MONTHS",
    "P3M": "THREE_MONTHS",
    "QUARTER": "THREE_MONTHS",
    "SEASON": "THREE_MONTHS",
    "SIX_MONTHS": "SIX_MONTHS",
    "P6M": "SIX_MONTHS",
    "YEAR": "ONE_YEAR",
    "1YEAR": "ONE_YEAR",
    "P1Y": "ONE_YEAR",
    "ONE_YEAR": "ONE_YEAR",
}

PERIOD_SLUGS = {
    "ONE_WEEK": "week",
    "ONE_MONTH": "month",
    "TWO_MONTHS": "2month",
    "THREE_MONTHS": "quarter",
    "SIX_MONTHS": "6month",
    "ONE_YEAR": "year",
}

PAYG_DURATION_BY_PERIOD = {
    "ONE_WEEK": "ONE_WEEK",
    "ONE_MONTH": "ONE_MONTH",
    "TWO_MONTHS": "TWO_MONTHS",
    "THREE_MONTHS": "THREE_MONTHS",
    "SIX_MONTHS": "SIX_MONTHS",
    "ONE_YEAR": "ONE_YEAR",
}
INTRO_MODES = {"FREE_TRIAL", "PAY_AS_YOU_GO", "PAY_UP_FRONT"}
INTRO_DURATIONS = {
    "THREE_DAYS",
    "ONE_WEEK",
    "TWO_WEEKS",
    "ONE_MONTH",
    "TWO_MONTHS",
    "THREE_MONTHS",
    "SIX_MONTHS",
    "ONE_YEAR",
}

VARIANT_SPECS: tuple[tuple[int, str, dict[str, Any] | None], ...] = (
    (0, "无试用", None),
    (1, "前三天免费", {"mode": "FREE_TRIAL", "duration": "THREE_DAYS", "number_of_periods": 1}),
    (2, "首周折扣", {"mode": "PAY_AS_YOU_GO", "duration": "ONE_WEEK", "number_of_periods": 1}),
    (3, "首周免费", {"mode": "FREE_TRIAL", "duration": "ONE_WEEK", "number_of_periods": 1}),
)


class ASCError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass(frozen=True)
class Localization:
    locale: str
    name: str
    description: str


@dataclass(frozen=True)
class IntroOffer:
    mode: str
    duration: str
    number_of_periods: int
    usd_price: str | None = None


@dataclass(frozen=True)
class SubscriptionSKU:
    product_id: str
    reference_name: str
    period: str
    group_level: int | None
    usd_price: str
    intro: IntroOffer | None = None
    localizations: tuple[Localization, ...] = ()
    review_note: str | None = None


@dataclass(frozen=True)
class Catalog:
    group_id: str
    base_territory: str
    price_scope: str
    family_sharable: bool
    available_in_all_territories: bool
    review_note: str | None
    default_localizations: tuple[Localization, ...]
    subscriptions: tuple[SubscriptionSKU, ...]
    bundle_id: str | None = None
    app_id: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class CreateOptions:
    dry_run: bool = False
    fill_missing: bool = False
    nearest_price: bool = False
    skip_availability: bool = False
    continue_on_error: bool = False
    product_ids: tuple[str, ...] = ()


@dataclass
class AuthConfig:
    issuer_id: str
    key_id: str
    private_key: str


def normalize_period(raw: str) -> str:
    key = raw.strip().upper().replace("-", "_").replace(" ", "")
    if key not in PERIOD_ALIASES:
        allowed = ", ".join(sorted(set(PERIOD_ALIASES.values())))
        raise ASCError(f"Unsupported subscription period {raw!r}. Allowed: {allowed}")
    return PERIOD_ALIASES[key]


def parse_money(raw: str, field_name: str) -> Decimal:
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, AttributeError) as error:
        raise ASCError(f"{field_name} is not a valid price: {raw!r}") from error
    if value <= 0:
        raise ASCError(f"{field_name} must be greater than 0: {raw!r}")
    return value


def prices_equal(left: str, right: str) -> bool:
    return Decimal(left) == Decimal(right)


def match_price_point(
    points: list[dict[str, Any]],
    usd_price: str,
    *,
    nearest: bool,
) -> tuple[dict[str, Any], bool]:
    target = parse_money(usd_price, "usd_price")
    exact: list[dict[str, Any]] = []
    nearest_point: dict[str, Any] | None = None
    nearest_delta: Decimal | None = None

    for point in points:
        raw_price = point.get("attributes", {}).get("customerPrice")
        if raw_price is None:
            continue
        current = Decimal(str(raw_price))
        if current == target:
            exact.append(point)
            continue
        delta = abs(current - target)
        if nearest_delta is None or delta < nearest_delta:
            nearest_delta = delta
            nearest_point = point

    if exact:
        return exact[0], False
    if nearest and nearest_point is not None:
        return nearest_point, True
    available = sorted(
        {
            str(point.get("attributes", {}).get("customerPrice"))
            for point in points
            if point.get("attributes", {}).get("customerPrice") is not None
        },
        key=lambda item: Decimal(item),
    )
    sample = ", ".join(available[:12])
    raise ASCError(
        f"No USA price point matches {usd_price}. Nearby values include: {sample}"
    )


def localization_from_dict(raw: dict[str, Any]) -> Localization:
    locale = str(raw.get("locale", "")).strip()
    name = str(raw.get("name", "")).strip()
    description = str(raw.get("description", "")).strip()
    if not locale or not name:
        raise ASCError("Each localization requires locale and name.")
    return Localization(locale=locale, name=name, description=description)


def intro_from_dict(raw: dict[str, Any] | None) -> IntroOffer | None:
    if not raw:
        return None
    mode = str(raw.get("mode", "")).strip().upper()
    duration = str(raw.get("duration", "")).strip().upper()
    periods = int(raw.get("number_of_periods", 1))
    if mode not in INTRO_MODES:
        raise ASCError(f"Unsupported intro mode {mode!r}. Allowed: {', '.join(sorted(INTRO_MODES))}")
    if duration not in INTRO_DURATIONS:
        raise ASCError(f"Unsupported intro duration {duration!r}.")
    if periods < 1:
        raise ASCError("intro.number_of_periods must be >= 1")
    usd_price = raw.get("usd_price")
    if mode in {"PAY_AS_YOU_GO", "PAY_UP_FRONT"} and not usd_price:
        raise ASCError(f"{mode} intro offers require usd_price.")
    return IntroOffer(
        mode=mode,
        duration=duration,
        number_of_periods=periods,
        usd_price=str(usd_price) if usd_price is not None else None,
    )


def coerce_paid_intro_duration(period: str, intro: IntroOffer | None) -> IntroOffer | None:
    if intro is None or intro.mode != "PAY_AS_YOU_GO":
        return intro
    required = PAYG_DURATION_BY_PERIOD.get(period)
    if required is None or intro.duration == required:
        return intro
    return IntroOffer(
        mode=intro.mode,
        duration=required,
        number_of_periods=intro.number_of_periods,
        usd_price=intro.usd_price,
    )


def sku_from_dict(raw: dict[str, Any], defaults: tuple[Localization, ...], review_note: str | None) -> SubscriptionSKU:
    product_id = str(raw.get("product_id", "")).strip()
    reference_name = str(raw.get("reference_name", "")).strip()
    if not product_id or " " in product_id:
        raise ASCError(f"Invalid product_id {product_id!r}. It cannot be empty or contain spaces.")
    if not reference_name:
        raise ASCError(f"Missing reference_name for {product_id}")
    if len(reference_name) > 64:
        raise ASCError(f"reference_name exceeds 64 characters: {reference_name}")

    localizations_raw = raw.get("localizations") or []
    localizations = tuple(localization_from_dict(item) for item in localizations_raw) or defaults
    if not localizations:
        raise ASCError(f"{product_id} needs at least one localization.")

    group_level = raw.get("group_level")
    period = normalize_period(str(raw.get("period", "")))
    intro = coerce_paid_intro_duration(period, intro_from_dict(raw.get("intro")))
    return SubscriptionSKU(
        product_id=product_id,
        reference_name=reference_name,
        period=period,
        group_level=int(group_level) if group_level is not None else None,
        usd_price=str(parse_money(str(raw.get("usd_price", "")), f"{product_id}.usd_price")),
        intro=intro,
        localizations=localizations,
        review_note=str(raw["review_note"]).strip() if raw.get("review_note") else review_note,
    )


def catalog_from_dict(payload: dict[str, Any], *, strict: bool = True) -> Catalog:
    if not isinstance(payload, dict):
        raise ASCError("SKU config must be a JSON object.")

    group_id = str(payload.get("group_id", "")).strip()
    price_scope = str(payload.get("price_scope", "usa")).strip().lower() or "usa"
    if price_scope not in {"usa", "all"}:
        raise ASCError("price_scope must be 'usa' or 'all'.")

    defaults = tuple(localization_from_dict(item) for item in payload.get("default_localizations", []))
    review_note = str(payload["review_note"]).strip() if payload.get("review_note") else None
    subscriptions_raw = payload.get("subscriptions") or []
    skus = tuple(sku_from_dict(item, defaults, review_note) for item in subscriptions_raw)
    product_ids = [sku.product_id for sku in skus]
    duplicates = sorted({item for item in product_ids if product_ids.count(item) > 1})
    if duplicates:
        raise ASCError(f"Duplicate product_id values: {', '.join(duplicates)}")
    if strict and not group_id:
        raise ASCError("group_id is required.")
    if strict and not skus:
        raise ASCError("subscriptions cannot be empty.")

    return Catalog(
        group_id=group_id,
        base_territory=str(payload.get("base_territory", "USA")).strip() or "USA",
        price_scope=price_scope,
        family_sharable=bool(payload.get("family_sharable", False)),
        available_in_all_territories=bool(payload.get("available_in_all_territories", True)),
        review_note=review_note,
        default_localizations=defaults,
        subscriptions=skus,
        bundle_id=str(payload["bundle_id"]).strip() if payload.get("bundle_id") else None,
        app_id=str(payload["app_id"]).strip() if payload.get("app_id") else None,
        name=str(payload["name"]).strip() if payload.get("name") else None,
    )


def localization_to_dict(item: Localization) -> dict[str, str]:
    return {"locale": item.locale, "name": item.name, "description": item.description}


def intro_to_dict(intro: IntroOffer) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": intro.mode,
        "duration": intro.duration,
        "number_of_periods": intro.number_of_periods,
    }
    if intro.usd_price:
        payload["usd_price"] = intro.usd_price
    return payload


def sku_to_dict(
    sku: SubscriptionSKU,
    defaults: tuple[Localization, ...] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "product_id": sku.product_id,
        "reference_name": sku.reference_name,
        "period": sku.period,
        "usd_price": sku.usd_price,
    }
    if sku.group_level is not None:
        payload["group_level"] = sku.group_level
    if sku.review_note:
        payload["review_note"] = sku.review_note
    if sku.intro is not None:
        payload["intro"] = intro_to_dict(sku.intro)
    if sku.localizations and sku.localizations != (defaults or ()):
        payload["localizations"] = [localization_to_dict(item) for item in sku.localizations]
    return payload


def catalog_to_dict(catalog: Catalog) -> dict[str, Any]:
    return {
        "name": catalog.name or "",
        "app_id": catalog.app_id or "",
        "bundle_id": catalog.bundle_id or "",
        "group_id": catalog.group_id,
        "base_territory": catalog.base_territory,
        "price_scope": catalog.price_scope,
        "family_sharable": catalog.family_sharable,
        "available_in_all_territories": catalog.available_in_all_territories,
        "review_note": catalog.review_note or "",
        "default_localizations": [localization_to_dict(item) for item in catalog.default_localizations],
        "subscriptions": [sku_to_dict(item, catalog.default_localizations) for item in catalog.subscriptions],
    }


def load_catalog(path: Path, *, strict: bool = True) -> Catalog:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return catalog_from_dict(payload, strict=strict)


def save_catalog(path: Path, catalog: Catalog) -> None:
    path.write_text(json.dumps(catalog_to_dict(catalog), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def scaffold_catalog(
    *,
    group_id: str,
    prefix: str,
    name_prefix: str,
    period: str,
    version: int,
    usd_price: str,
    intro_usd: str | None,
    start_level: int,
    display_name: str,
    display_description: str,
    locale: str = "en-US",
    extra_localizations: list[dict[str, str]] | None = None,
    review_note: str | None = None,
    price_scope: str = "usa",
    variants: tuple[tuple[int, str, dict[str, Any] | None], ...] | None = None,
) -> dict[str, Any]:
    apple_period = normalize_period(period)
    slug = PERIOD_SLUGS[apple_period]
    parse_money(usd_price, "usd")
    matrix = variants if variants is not None else VARIANT_SPECS
    subscriptions: list[dict[str, Any]] = []
    for offset, label, intro in matrix:
        item: dict[str, Any] = {
            "product_id": f"{prefix}.{slug}.{version}.{offset}",
            "reference_name": f"{name_prefix}-{slug}-{version}.{offset}-{label}",
            "period": apple_period,
            "group_level": start_level + offset,
            "usd_price": usd_price,
        }
        if intro is not None:
            offer = dict(intro)
            if offer["mode"] in {"PAY_AS_YOU_GO", "PAY_UP_FRONT"}:
                if not intro_usd:
                    raise ASCError("PAY_AS_YOU_GO variants require intro USD price.")
                parse_money(intro_usd, "intro-usd")
                offer["usd_price"] = intro_usd
            item["intro"] = offer
        subscriptions.append(item)
    localizations = [{"locale": locale, "name": display_name, "description": display_description}]
    if extra_localizations:
        localizations.extend(extra_localizations)
    return {
        "group_id": group_id,
        "base_territory": "USA",
        "price_scope": price_scope,
        "family_sharable": False,
        "available_in_all_territories": True,
        "review_note": review_note or "",
        "default_localizations": localizations,
        "subscriptions": subscriptions,
    }


def subscription_create_payload(sku: SubscriptionSKU, group_id: str, catalog: Catalog) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        "name": sku.reference_name,
        "productId": sku.product_id,
        "subscriptionPeriod": sku.period,
    }
    if catalog.family_sharable:
        attributes["familySharable"] = True
    if sku.group_level is not None:
        attributes["groupLevel"] = sku.group_level
    if sku.review_note:
        attributes["reviewNote"] = sku.review_note
    return {
        "data": {
            "type": "subscriptions",
            "attributes": attributes,
            "relationships": {
                "group": {"data": {"type": "subscriptionGroups", "id": group_id}}
            },
        }
    }


def localization_payload(sku_id: str, localization: Localization) -> dict[str, Any]:
    return {
        "data": {
            "type": "subscriptionLocalizations",
            "attributes": {
                "name": localization.name,
                "locale": localization.locale,
                "description": localization.description,
            },
            "relationships": {
                "subscription": {"data": {"type": "subscriptions", "id": sku_id}}
            },
        }
    }


def price_payload(sku_id: str, price_point_id: str) -> dict[str, Any]:
    return {
        "data": {
            "type": "subscriptionPrices",
            "relationships": {
                "subscription": {"data": {"type": "subscriptions", "id": sku_id}},
                "subscriptionPricePoint": {
                    "data": {"type": "subscriptionPricePoints", "id": price_point_id}
                },
            },
        }
    }


def intro_payload(
    sku_id: str,
    intro: IntroOffer,
    *,
    territory_id: str | None,
    price_point_id: str | None,
) -> dict[str, Any]:
    relationships: dict[str, Any] = {
        "subscription": {"data": {"type": "subscriptions", "id": sku_id}}
    }
    if territory_id:
        relationships["territory"] = {"data": {"type": "territories", "id": territory_id}}
    if price_point_id:
        relationships["subscriptionPricePoint"] = {
            "data": {"type": "subscriptionPricePoints", "id": price_point_id}
        }
    return {
        "data": {
            "type": "subscriptionIntroductoryOffers",
            "attributes": {
                "duration": intro.duration,
                "offerMode": intro.mode,
                "numberOfPeriods": intro.number_of_periods,
                "startDate": date.today().isoformat(),
            },
            "relationships": relationships,
        }
    }


def availability_payload(sku_id: str, territory_ids: list[str], available_in_new: bool) -> dict[str, Any]:
    return {
        "data": {
            "type": "subscriptionAvailabilities",
            "attributes": {"availableInNewTerritories": available_in_new},
            "relationships": {
                "subscription": {"data": {"type": "subscriptions", "id": sku_id}},
                "availableTerritories": {
                    "data": [
                        {"type": "territories", "id": territory_id}
                        for territory_id in territory_ids
                    ]
                },
            },
        }
    }


APP_NAME = "ASC SKU"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundled_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    if is_frozen():
        if sys.platform == "darwin":
            path = Path.home() / "Library" / "Application Support" / APP_NAME
        elif sys.platform == "win32":
            path = Path(os.environ.get("APPDATA") or str(Path.home())) / APP_NAME
        else:
            path = Path.home() / ".config" / "asc-sku"
        path.mkdir(parents=True, exist_ok=True)
        (path / "projects").mkdir(exist_ok=True)
        return path
    return Path(__file__).resolve().parent


def seed_user_data() -> None:
    if not is_frozen():
        return
    source = bundled_root() / "projects"
    destination = data_dir() / "projects"
    if not source.is_dir():
        return
    for item in source.glob("*.json"):
        target = destination / item.name
        if not target.exists():
            shutil.copy2(item, target)


def save_credentials(issuer_id: str, key_id: str, p8_path: Path, directory: Path | None = None) -> Path:
    dest_dir = directory or data_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    source = p8_path.expanduser().resolve()
    if not source.is_file():
        raise ASCError(f"Private key not found: {source}")
    destination = dest_dir / source.name
    if source != destination:
        shutil.copy2(source, destination)
    env_path = dest_dir / ".env"
    env_path.write_text(
        (
            f"ASC_ISSUER_ID={issuer_id.strip()}\n"
            f"ASC_KEY_ID={key_id.strip()}\n"
            f"ASC_KEY_P8_PATH={destination}\n"
        ),
        encoding="utf-8",
    )
    return destination


PROJECT_DIR = data_dir()


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def discover_p8(directory: Path) -> Path | None:
    named = sorted(path for path in directory.glob("AuthKey_*.p8") if path.is_file())
    if len(named) == 1:
        return named[0]
    if len(named) > 1:
        names = ", ".join(path.name for path in named)
        raise ASCError(f"Multiple AuthKey_*.p8 files found ({names}). Pass --p8.")
    all_keys = sorted(path for path in directory.glob("*.p8") if path.is_file())
    if len(all_keys) == 1:
        return all_keys[0]
    if len(all_keys) > 1:
        names = ", ".join(path.name for path in all_keys)
        raise ASCError(f"Multiple .p8 files found ({names}). Pass --p8.")
    return None


def key_id_from_p8_name(path: Path) -> str | None:
    match = re.fullmatch(r"AuthKey_([A-Z0-9]+)\.p8", path.name)
    return match.group(1) if match else None


def load_auth(args: argparse.Namespace) -> AuthConfig:
    load_env_file(PROJECT_DIR / ".env")
    load_env_file(PROJECT_DIR / "credentials.env")
    issuer_id = (args.issuer_id or os.environ.get("ASC_ISSUER_ID") or "").strip()
    key_id = (args.key_id or os.environ.get("ASC_KEY_ID") or "").strip()
    key_path = (
        args.p8
        or os.environ.get("ASC_KEY_P8_PATH")
        or os.environ.get("ASC_PRIVATE_KEY_PATH")
        or ""
    ).strip()
    if not key_path:
        discovered = discover_p8(PROJECT_DIR)
        if discovered is not None:
            key_path = str(discovered)
            if not key_id:
                key_id = key_id_from_p8_name(discovered) or ""
    missing = [
        name
        for name, value in (
            ("ASC_ISSUER_ID", issuer_id),
            ("ASC_KEY_ID", key_id),
            ("ASC_KEY_P8_PATH", key_path),
        )
        if not value
    ]
    if missing:
        raise ASCError(
            "Missing App Store Connect credentials: "
            + ", ".join(missing)
            + ". Put AuthKey_XXXXXXXXXX.p8 in this directory and set ASC_ISSUER_ID."
        )
    path = Path(key_path).expanduser()
    if not path.is_file():
        raise ASCError(f"Private key file not found: {path.name}")
    private_key = path.read_text(encoding="utf-8")
    if "BEGIN PRIVATE KEY" not in private_key:
        raise ASCError("The .p8 file does not look like a PKCS#8 private key.")
    return AuthConfig(issuer_id=issuer_id, key_id=key_id, private_key=private_key)


class ASCClient:
    def __init__(self, auth: AuthConfig) -> None:
        self._auth = auth
        self._token = ""
        self._token_exp = 0.0
        self._session = requests.Session()

    def _mint_token(self) -> str:
        now = int(time.time())
        payload = {
            "iss": self._auth.issuer_id,
            "iat": now,
            "exp": now + TOKEN_LIFETIME_SECONDS,
            "aud": "appstoreconnect-v1",
        }
        headers = {"alg": "ES256", "kid": self._auth.key_id, "typ": "JWT"}
        token = jwt.encode(payload, self._auth.private_key, algorithm="ES256", headers=headers)
        if isinstance(token, bytes):
            token = token.decode("utf-8")
        self._token = token
        self._token_exp = float(payload["exp"])
        return token

    def _authorization(self) -> str:
        if not self._token or time.time() > self._token_exp - 60:
            self._mint_token()
        return f"Bearer {self._token}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = path if path.startswith("https://") else f"{ASC_HOST}{path}"
        host = urlparse(url).netloc
        if host != "api.appstoreconnect.apple.com":
            raise ASCError(f"Refusing to call unexpected host: {host}")

        last_error: ASCError | None = None
        for attempt in range(6):
            response = self._session.request(
                method,
                url,
                headers={
                    "Authorization": self._authorization(),
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                params=params,
                json=json_body,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code in {429, 500, 502, 503, 504}:
                wait_for = float(response.headers.get("Retry-After", min(2 ** attempt, 30)))
                time.sleep(wait_for)
                last_error = self._error_from_response(response)
                continue
            if response.status_code >= 400:
                raise self._error_from_response(response)
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()
        raise last_error or ASCError("App Store Connect request failed after retries.")

    @staticmethod
    def _error_from_response(response: requests.Response) -> ASCError:
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}
        details: list[str] = []
        for error in payload.get("errors", []) if isinstance(payload, dict) else []:
            detail = error.get("detail") or error.get("title") or json.dumps(error, ensure_ascii=False)
            details.append(str(detail))
        message = "; ".join(details) or f"HTTP {response.status_code}"
        return ASCError(message, status_code=response.status_code, body=payload)

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("GET", path, params=params)

    def post(self, path: str, json_body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, json_body=json_body)

    def paginate(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        next_path: str | None = path
        next_params = params
        while next_path:
            payload = self.get(next_path, next_params)
            chunk = payload.get("data", [])
            if isinstance(chunk, list):
                items.extend(chunk)
            elif isinstance(chunk, dict):
                items.append(chunk)
            next_url = (payload.get("links") or {}).get("next")
            next_path = next_url
            next_params = None
        return items


def format_errors(error: ASCError) -> str:
    if error.status_code is None:
        return str(error)
    return f"[{error.status_code}] {error}"


def print_table(rows: list[dict[str, str]], columns: list[tuple[str, str]]) -> None:
    if not rows:
        print("(empty)")
        return
    widths = {
        key: max(len(title), *(len(str(row.get(key, ""))) for row in rows))
        for key, title in columns
    }
    header = "  ".join(title.ljust(widths[key]) for key, title in columns)
    print(header)
    print("  ".join("-" * widths[key] for key, _title in columns))
    for row in rows:
        print("  ".join(str(row.get(key, "")).ljust(widths[key]) for key, _title in columns))


def fetch_apps(client: ASCClient) -> list[dict[str, str]]:
    apps = client.paginate("/v1/apps", {"limit": 200})
    return [
        {
            "id": app.get("id", ""),
            "bundle": str((app.get("attributes") or {}).get("bundleId", "")),
            "name": str((app.get("attributes") or {}).get("name", "")),
        }
        for app in apps
    ]


def fetch_groups(client: ASCClient, app_id: str) -> list[dict[str, str]]:
    groups = client.paginate(f"/v1/apps/{app_id}/subscriptionGroups", {"limit": 200})
    return [
        {
            "id": group.get("id", ""),
            "name": str((group.get("attributes") or {}).get("referenceName", "")),
        }
        for group in groups
    ]


def fetch_skus(client: ASCClient, group_id: str) -> list[dict[str, str]]:
    items = client.paginate(f"/v1/subscriptionGroups/{group_id}/subscriptions", {"limit": 200})
    rows = [
        {
            "level": str((item.get("attributes") or {}).get("groupLevel", "")),
            "name": str((item.get("attributes") or {}).get("name", "")),
            "product": str((item.get("attributes") or {}).get("productId", "")),
            "period": str((item.get("attributes") or {}).get("subscriptionPeriod", "")),
            "state": str((item.get("attributes") or {}).get("state", "")),
            "id": item.get("id", ""),
        }
        for item in items
    ]
    rows.sort(key=lambda row: int(row["level"] or 10**9))
    return rows


def cmd_list_apps(client: ASCClient) -> int:
    print_table(fetch_apps(client), [("id", "App ID"), ("bundle", "Bundle ID"), ("name", "Name")])
    return 0


def resolve_app_id(client: ASCClient, *, app_id: str | None, bundle_id: str | None) -> str:
    if app_id:
        return app_id
    if not bundle_id:
        raise ASCError("Provide --app-id or --bundle-id.")
    apps = client.paginate("/v1/apps", {"filter[bundleId]": bundle_id, "limit": 200})
    if not apps:
        raise ASCError(f"No app found for bundle id {bundle_id}")
    return str(apps[0]["id"])


def cmd_list_groups(client: ASCClient, args: argparse.Namespace) -> int:
    app_id = resolve_app_id(client, app_id=args.app_id, bundle_id=args.bundle_id)
    print_table(fetch_groups(client, app_id), [("id", "Group ID"), ("name", "Reference Name")])
    return 0


def cmd_list_skus(client: ASCClient, group_id: str) -> int:
    print_table(
        fetch_skus(client, group_id),
        [
            ("level", "Level"),
            ("name", "Reference Name"),
            ("product", "Product ID"),
            ("period", "Period"),
            ("state", "State"),
            ("id", "ASC ID"),
        ],
    )
    return 0


def existing_product_map(client: ASCClient, group_id: str) -> dict[str, dict[str, Any]]:
    items = client.paginate(f"/v1/subscriptionGroups/{group_id}/subscriptions", {"limit": 200})
    mapping: dict[str, dict[str, Any]] = {}
    for item in items:
        product_id = str((item.get("attributes") or {}).get("productId", "")).strip()
        if product_id:
            mapping[product_id] = item
    return mapping


def create_subscription(client: ASCClient, sku: SubscriptionSKU, catalog: Catalog) -> str:
    response = client.post("/v1/subscriptions", subscription_create_payload(sku, catalog.group_id, catalog))
    sku_id = str((response.get("data") or {}).get("id", ""))
    if not sku_id:
        raise ASCError(f"Create succeeded but returned no id for {sku.product_id}")
    return sku_id


def add_localizations(client: ASCClient, sku_id: str, localizations: tuple[Localization, ...]) -> None:
    for localization in localizations:
        try:
            client.post("/v1/subscriptionLocalizations", localization_payload(sku_id, localization))
        except ASCError as error:
            if error.status_code == 409:
                continue
            raise


def fetch_price_points(client: ASCClient, sku_id: str, territory: str) -> list[dict[str, Any]]:
    return client.paginate(
        f"/v1/subscriptions/{sku_id}/pricePoints",
        {"filter[territory]": territory, "limit": 200, "include": "territory"},
    )


def territory_id_of(point: dict[str, Any]) -> str | None:
    data = ((point.get("relationships") or {}).get("territory") or {}).get("data") or {}
    territory_id = data.get("id")
    return str(territory_id) if territory_id else None


def post_price(client: ASCClient, sku_id: str, price_point_id: str) -> None:
    try:
        client.post("/v1/subscriptionPrices", price_payload(sku_id, price_point_id))
    except ASCError as error:
        if error.status_code == 409:
            return
        raise


def post_intro(
    client: ASCClient,
    sku_id: str,
    intro: IntroOffer,
    *,
    territory_id: str | None,
    price_point_id: str | None,
) -> None:
    try:
        client.post(
            "/v1/subscriptionIntroductoryOffers",
            intro_payload(
                sku_id,
                intro,
                territory_id=territory_id,
                price_point_id=price_point_id,
            ),
        )
    except ASCError as error:
        if error.status_code == 409:
            detail = str(error).lower()
            if "not supported" in detail or "invalid" in detail:
                raise
            return
        raise


def list_territory_ids(client: ASCClient) -> list[str]:
    territories = client.paginate("/v1/territories", {"limit": 200})
    return [str(item["id"]) for item in territories if item.get("id")]


def equalized_price_points(client: ASCClient, price_point_id: str) -> list[dict[str, Any]]:
    return client.paginate(
        f"/v1/subscriptionPricePoints/{price_point_id}/equalizations",
        {"limit": 200, "include": "territory"},
    )


def set_prices(
    client: ASCClient,
    sku_id: str,
    usd_price: str,
    *,
    territory: str,
    price_scope: str,
    nearest: bool,
) -> str:
    points = fetch_price_points(client, sku_id, territory)
    selected, used_nearest = match_price_point(points, usd_price, nearest=nearest)
    selected_id = str(selected["id"])
    selected_price = str(selected.get("attributes", {}).get("customerPrice"))
    if used_nearest:
        print(f"    ! {usd_price} is not on Apple's ladder; using {selected_price}")
    post_price(client, sku_id, selected_id)
    if price_scope != "all":
        return selected_price

    equalizations = equalized_price_points(client, selected_id)
    print(f"    prices: USA {selected_price}, equalizing {len(equalizations)} territories")
    for index, point in enumerate(equalizations, start=1):
        point_id = str(point.get("id", ""))
        if not point_id or territory_id_of(point) == territory:
            continue
        post_price(client, sku_id, point_id)
        if index % 25 == 0:
            print(f"    prices: {index}/{len(equalizations)}")
        time.sleep(0.05)
    return selected_price


def add_intro_offer(
    client: ASCClient,
    sku_id: str,
    intro: IntroOffer,
    *,
    territory: str,
    price_scope: str,
    nearest: bool,
) -> None:
    selected: dict[str, Any] | None = None
    if intro.usd_price:
        points = fetch_price_points(client, sku_id, territory)
        selected, used_nearest = match_price_point(points, intro.usd_price, nearest=nearest)
        if used_nearest:
            print(
                "    ! intro "
                f"{intro.usd_price} is not on Apple's ladder; using "
                f"{selected.get('attributes', {}).get('customerPrice')}"
            )

    if price_scope != "all":
        post_intro(
            client,
            sku_id,
            intro,
            territory_id=territory,
            price_point_id=str(selected["id"]) if selected else None,
        )
        return

    if selected is None:
        territory_ids = list_territory_ids(client)
        print(f"    intro: {intro.mode}/{intro.duration} x {len(territory_ids)} territories")
        for index, territory_id in enumerate(territory_ids, start=1):
            post_intro(
                client,
                sku_id,
                intro,
                territory_id=territory_id,
                price_point_id=None,
            )
            if index % 25 == 0:
                print(f"    intro: {index}/{len(territory_ids)}")
            time.sleep(0.05)
        return

    equalizations = equalized_price_points(client, str(selected["id"]))
    targets = [selected, *equalizations]
    print(f"    intro: {intro.mode}/{intro.duration} @ {intro.usd_price} x {len(targets)} territories")
    seen: set[str] = set()
    for index, point in enumerate(targets, start=1):
        point_id = str(point.get("id", ""))
        current_territory = territory_id_of(point) or (territory if point is selected else None)
        if not point_id or not current_territory or current_territory in seen:
            continue
        seen.add(current_territory)
        post_intro(
            client,
            sku_id,
            intro,
            territory_id=current_territory,
            price_point_id=point_id,
        )
        if index % 25 == 0:
            print(f"    intro: {index}/{len(targets)}")
        time.sleep(0.05)


def set_availability(client: ASCClient, sku_id: str, available_in_new: bool) -> None:
    territory_ids = list_territory_ids(client)
    client.post(
        "/v1/subscriptionAvailabilities",
        availability_payload(sku_id, territory_ids, available_in_new),
    )


def create_one(
    client: ASCClient,
    sku: SubscriptionSKU,
    catalog: Catalog,
    existing: dict[str, dict[str, Any]],
    *,
    dry_run: bool,
    fill_missing: bool,
    nearest: bool,
    skip_availability: bool,
) -> str:
    current = existing.get(sku.product_id)
    if current and not fill_missing:
        return "skipped-exists"
    if dry_run:
        action = "fill" if current else "create"
        intro = "none"
        if sku.intro is not None:
            intro = f"{sku.intro.mode}/{sku.intro.duration}"
            if sku.intro.usd_price:
                intro += f"@{sku.intro.usd_price}"
        print(
            f"  [{action}] {sku.product_id}  {sku.reference_name}  "
            f"{sku.period}  USD {sku.usd_price}  intro={intro}  prices={catalog.price_scope}"
        )
        return "dry-run"

    sku_id = str(current["id"]) if current else create_subscription(client, sku, catalog)
    add_localizations(client, sku_id, sku.localizations)
    if not skip_availability:
        try:
            set_availability(client, sku_id, catalog.available_in_all_territories)
        except ASCError as error:
            print(f"    ! availability: {format_errors(error)}")
    set_prices(
        client,
        sku_id,
        sku.usd_price,
        territory=catalog.base_territory,
        price_scope=catalog.price_scope,
        nearest=nearest,
    )
    if sku.intro is not None:
        add_intro_offer(
            client,
            sku_id,
            sku.intro,
            territory=catalog.base_territory,
            price_scope=catalog.price_scope,
            nearest=nearest,
        )
    return "updated" if current else "created"


def create_from_catalog(client: ASCClient, catalog: Catalog, options: CreateOptions) -> int:
    if not catalog.group_id:
        raise ASCError("group_id is required.")
    if not catalog.subscriptions:
        raise ASCError("subscriptions cannot be empty.")
    existing = existing_product_map(client, catalog.group_id)
    wanted = {item.strip() for item in options.product_ids if item.strip()}
    subscriptions = catalog.subscriptions
    if wanted:
        subscriptions = tuple(sku for sku in subscriptions if sku.product_id in wanted)
        missing = sorted(wanted - {sku.product_id for sku in subscriptions})
        if missing:
            raise ASCError(f"product_id not in config: {', '.join(missing)}")
    print(
        f"Group {catalog.group_id}: {len(existing)} existing SKUs, "
        f"{len(subscriptions)} in this run"
    )
    counts = {"created": 0, "updated": 0, "skipped-exists": 0, "dry-run": 0, "failed": 0}
    for sku in subscriptions:
        try:
            result = create_one(
                client,
                sku,
                catalog,
                existing,
                dry_run=options.dry_run,
                fill_missing=options.fill_missing,
                nearest=options.nearest_price,
                skip_availability=options.skip_availability,
            )
            counts[result] = counts.get(result, 0) + 1
            if result != "dry-run":
                print(f"  [{result}] {sku.product_id}")
        except ASCError as error:
            counts["failed"] += 1
            print(f"  [failed] {sku.product_id}: {format_errors(error)}")
            if not options.continue_on_error:
                return 1
    print(
        "Done: "
        + ", ".join(f"{key}={value}" for key, value in counts.items() if value)
    )
    return 1 if counts["failed"] else 0


def cmd_create(client: ASCClient, args: argparse.Namespace) -> int:
    catalog = load_catalog(Path(args.config).expanduser())
    return create_from_catalog(
        client,
        catalog,
        CreateOptions(
            dry_run=args.dry_run,
            fill_missing=args.fill_missing,
            nearest_price=args.nearest_price,
            skip_availability=args.skip_availability,
            continue_on_error=args.continue_on_error,
            product_ids=tuple(args.product_id or ()),
        ),
    )


def cmd_scaffold(args: argparse.Namespace) -> int:
    extra = []
    if args.display_name_zh:
        extra.append(
            {
                "locale": "zh-Hans",
                "name": args.display_name_zh,
                "description": args.display_description_zh or args.display_description,
            }
        )
    catalog = scaffold_catalog(
        group_id=args.group_id,
        prefix=args.prefix,
        name_prefix=args.name_prefix,
        period=args.period,
        version=args.version,
        usd_price=args.usd,
        intro_usd=args.intro_usd,
        start_level=args.start_level,
        display_name=args.display_name,
        display_description=args.display_description,
        extra_localizations=extra or None,
        review_note=args.review_note,
        price_scope=args.price_scope,
    )
    text = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).expanduser().write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        sys.stdout.write(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create App Store Connect subscription SKUs in bulk.")
    parser.add_argument("--issuer-id", help="Overrides ASC_ISSUER_ID")
    parser.add_argument("--key-id", help="Overrides ASC_KEY_ID")
    parser.add_argument("--p8", help="Overrides ASC_KEY_P8_PATH")
    sub = parser.add_subparsers(dest="command", required=True)

    list_apps = sub.add_parser("list-apps", help="List apps visible to the API key")
    list_apps.set_defaults(handler="list-apps")

    list_groups = sub.add_parser("list-groups", help="List subscription groups for an app")
    list_groups.add_argument("--bundle-id")
    list_groups.add_argument("--app-id")
    list_groups.set_defaults(handler="list-groups")

    list_skus = sub.add_parser("list-skus", help="List SKUs in a subscription group")
    list_skus.add_argument("--group-id", required=True)
    list_skus.set_defaults(handler="list-skus")

    create = sub.add_parser("create", help="Create SKUs from a JSON catalog")
    create.add_argument("--config", required=True, help="Path to skus.json")
    create.add_argument("--dry-run", action="store_true")
    create.add_argument("--fill-missing", action="store_true", help="Complete localization/price/intro for existing product IDs")
    create.add_argument("--product-id", action="append", default=[], help="Limit to one or more product IDs")
    create.add_argument("--nearest-price", action="store_true", help="Use the closest Apple price point when USD is not exact")
    create.add_argument("--skip-availability", action="store_true")
    create.add_argument("--continue-on-error", action="store_true")
    create.set_defaults(handler="create")

    scaffold = sub.add_parser("scaffold", help="Generate a SKU matrix JSON from naming flags")
    scaffold.add_argument("--group-id", required=True)
    scaffold.add_argument("--prefix", required=True, help="Product ID prefix, e.g. com.example.vip")
    scaffold.add_argument("--name-prefix", required=True, help="Reference name prefix")
    scaffold.add_argument("--period", required=True, help="week / month / quarter / year")
    scaffold.add_argument("--version", type=int, default=1)
    scaffold.add_argument("--usd", required=True)
    scaffold.add_argument("--intro-usd", help="Required when the matrix includes a paid intro")
    scaffold.add_argument("--start-level", type=int, default=1)
    scaffold.add_argument("--display-name", required=True, help="Customer-facing name, e.g. VIP")
    scaffold.add_argument("--display-description", default="")
    scaffold.add_argument("--display-name-zh")
    scaffold.add_argument("--display-description-zh")
    scaffold.add_argument("--review-note", default="")
    scaffold.add_argument("--price-scope", choices=("usa", "all"), default="usa")
    scaffold.add_argument("-o", "--output")
    scaffold.set_defaults(handler="scaffold")

    gui = sub.add_parser("gui", help="Open the desktop GUI")
    gui.set_defaults(handler="gui")
    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw or raw[0] in {"gui", "--gui"}:
        from gui import run_gui

        return run_gui()
    parser = build_parser()
    args = parser.parse_args(raw)
    try:
        if args.handler == "gui":
            from gui import run_gui

            return run_gui()
        if args.handler == "scaffold":
            return cmd_scaffold(args)
        client = ASCClient(load_auth(args))
        if args.handler == "list-apps":
            return cmd_list_apps(client)
        if args.handler == "list-groups":
            return cmd_list_groups(client, args)
        if args.handler == "list-skus":
            return cmd_list_skus(client, args.group_id)
        if args.handler == "create":
            return cmd_create(client, args)
        parser.error(f"Unknown command {args.handler}")
        return 2
    except ASCError as error:
        print(f"error: {format_errors(error)}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("aborted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
