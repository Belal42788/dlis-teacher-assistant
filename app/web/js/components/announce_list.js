import { h, icon } from "../dom.js";
import { t } from "../i18n.js";
import { fmtDate } from "../labels.js";

const audLabel = (a) => t(`an_aud_${a}`);

// One announcement as a card. `onDelete` is given only to the administration.
export function announceCard(a, onDelete, onEdit) {
  return h("div", { class: `ann${a.active ? "" : " old"}` },
    h("b", {}, a.title),
    a.image_url ? h("img", { class: "ann-img", src: a.image_url, alt: "" }) : null,
    a.body ? h("p", { class: "pre" }, a.body) : null,
    h("div", { class: "muted small" }, fmtDate(a.starts_on, { day: "numeric", month: "long" }), a.ends_on ? ` → ${fmtDate(a.ends_on, { day: "numeric", month: "long" })}` : "", a.active ? "" : ` · ${t("an_ended")}`),
    onEdit || onDelete ? h("div", { class: "row" },
      onEdit ? h("button", { class: "btn small", onClick: () => onEdit(a) }, icon("edit"), t("an_edit")) : null,
      onDelete ? h("button", { class: "btn small ghost", onClick: () => onDelete(a) }, icon("trash"), t("remove")) : null) : null);
}
