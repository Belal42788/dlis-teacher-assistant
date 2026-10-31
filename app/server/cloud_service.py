"""Connection to the school's free Supabase server (Phase 12). Settings live in cloud.json in the data folder;
the password is never saved, only the refresh token."""
from __future__ import annotations

from ..core.cloud import Cloud, clean_url
from ..core.errors import AppError

ROLES = ("admin", "teacher", "parent", "none")


class CloudMixin:
    def _cloud_path(self):
        return self._need_store().root / "cloud.json"

    def _cloud_cfg(self) -> dict:
        d = self._need_store().read_json(self._cloud_path(), {}, check=lambda x: isinstance(x, dict) or (_ for _ in ()).throw(ValueError("bad"))) or {}
        return {"url": str(d.get("url", "")), "key": str(d.get("key", "")), "email": str(d.get("email", "")), "refresh": str(d.get("refresh", "")), "role": str(d.get("role", ""))}

    def _cloud_save(self, cfg: dict) -> None:
        self._need_store().write_json(self._cloud_path(), cfg)

    def _cloud_client(self) -> Cloud:
        cfg = self._cloud_cfg()
        c = getattr(self, "_cloud_live", None)
        if c is None or (c.url, c.key) != (cfg["url"], cfg["key"]):
            c = self._cloud_live = Cloud(cfg["url"], cfg["key"], cfg["refresh"])
        return c

    def get_cloud(self) -> dict:
        cfg = self._cloud_cfg()
        return {"url": cfg["url"], "key_set": bool(cfg["key"]), "email": cfg["email"], "signed_in": bool(cfg["refresh"]), "role": cfg["role"]}

    def put_cloud(self, b: dict) -> dict:
        cfg = self._cloud_cfg()
        url = clean_url(str(b.get("url", cfg["url"])))
        key = str(b.get("key") or "").strip() or cfg["key"]
        if (url, key) != (cfg["url"], cfg["key"]):
            cfg.update(refresh="", role="")
            self._cloud_live = None
        cfg.update(url=url, key=key)
        self._cloud_save(cfg)
        return self.get_cloud()

    def cloud_login(self, b: dict) -> dict:
        email, password = str(b.get("email", "")).strip(), str(b.get("password", ""))
        if not email or not password:
            raise AppError("cloud_bad_login", "Type the email and the password.", status=400)
        c = self._cloud_client()
        c.sign_in(email, password)
        role = c.role()
        cfg = self._cloud_cfg()
        cfg.update(email=email, refresh=c.refresh, role=role)
        self._cloud_save(cfg)
        return self.get_cloud()

    def cloud_logout(self) -> dict:
        cfg = self._cloud_cfg()
        cfg.update(refresh="", role="")
        self._cloud_save(cfg)
        self._cloud_live = None
        return self.get_cloud()

    def cloud_test(self) -> dict:
        """Is the server reachable and are the school's tables there? (signed-in teachers/admins only see rows)"""
        c = self._cloud_client()
        role = c.role()
        tables = {}
        for t in ("announcements", "students", "grades", "publications", "week_plans"):
            c.select(t, "select=*&limit=1")
            tables[t] = True
        cfg = self._cloud_cfg()
        cfg["role"] = role
        cfg["refresh"] = c.refresh or cfg["refresh"]
        self._cloud_save(cfg)
        return {"ok": True, "role": role, "tables": tables}
