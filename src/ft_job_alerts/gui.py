from __future__ import annotations

import os
import sys
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText
from argparse import Namespace
from typing import Any, List

from .config import load_config
from .profiles import get_categories, get_domains, get_default_profile
from .storage import init_db, query_offers
from .exporter import export_txt, export_md, export_csv, export_jsonl
from .cli import cmd_fetch


_CATEGORIES: List[tuple[str, list[str]]] = get_categories()
_DOMAINS: List[tuple[str, List[str]]] = get_domains()


def _open_folder(path: str) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])
    except Exception:
        pass


def _ai_prompt_text(out_path: str) -> str:
    return (
        "Conseil — Analyse avec un agent IA (gratuit)\n"
        "1) Ouvrez Google AI Studio (https://aistudio.google.com) → ‘Create a prompt’.\n"
        f"2) Ouvrez le fichier exporté ({out_path}) et copiez le contenu.\n"
        "3) Collez-le dans le chat puis utilisez un prompt comme: \n\n"
        "Vous êtes mon assistant emploi. Profil: junior robotique (ROS2/C++/vision), mobilité limitée.\n"
        "À partir des offres collées, propose un top 10 trié par pertinence, avec:\n"
        "- résumé en 2 lignes,\n- principaux critères correspondants (ROS2/vision/robot brands/remote),\n"
        "- score 0–10 et raison,\n- questions à poser au recruteur.\n\n"
        "Ensuite, liste 5 entreprises à suivre (fréquence des offres).\n"
    )


class App(ttk.Frame):
    def __init__(self, master: tk.Tk, profile_name: str | None = None):
        super().__init__(master)
        self.master = master
        self.pack(fill=tk.BOTH, expand=True)
        self.cfg = load_config()
        # Load profile (default or named)
        self.profile = get_default_profile(profile_name) or {}
        self._build_ui()

    def _build_ui(self):
        self.master.title("FT Job Alerts — Assistant Graphique")
        self.master.minsize(760, 560)
        self.master.geometry("860x640")

        # Top bar (no simulate/real mode banner anymore)
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=10, pady=8)
        ttk.Label(top, text="France Travail — Recherche d'offres").pack(side=tk.LEFT)

        # Domain & Categories
        frm_cat = ttk.LabelFrame(self, text="Domaine et catégories")
        frm_cat.pack(fill=tk.X, padx=10, pady=8)
        ttk.Label(frm_cat, text="Domaine:").grid(row=0, column=0, sticky="e")
        # Determine default domain label
        _dom_default = (self.profile.get("domain") if isinstance(self.profile, dict) else None) or (_DOMAINS[1][0] if len(_DOMAINS) > 1 else _DOMAINS[0][0])
        self.var_domain = tk.StringVar(value=_dom_default)
        self.opt_domain = ttk.OptionMenu(frm_cat, self.var_domain, _dom_default, *[d[0] for d in _DOMAINS], command=lambda *_: self._apply_domain_defaults())
        self.opt_domain.grid(row=0, column=1, sticky="w", padx=6)
        self.var_cats: list[tk.BooleanVar] = []
        for i, (label, _kw) in enumerate(_CATEGORIES):
            var = tk.BooleanVar(value=False)
            self.var_cats.append(var)
            cb = ttk.Checkbutton(frm_cat, text=label, variable=var)
            cb.grid(row=1 + (i // 2), column=i % 2, sticky="w", padx=6, pady=2)

        # Keywords extra
        frm_kw = ttk.Frame(self)
        frm_kw.pack(fill=tk.X, padx=10, pady=4)
        ttk.Label(frm_kw, text="Mots-clés (séparés par des virgules):").pack(anchor="w")
        self.ent_kw = ttk.Entry(frm_kw)
        self.ent_kw.pack(fill=tk.X)
        self.lbl_kw_hint = ttk.Label(frm_kw, text="", foreground="#777")
        self.lbl_kw_hint.pack(anchor="w", pady=2)

        # Location
        frm_loc = ttk.LabelFrame(self, text="Localisation (optionnel)")
        frm_loc.pack(fill=tk.X, padx=10, pady=8)
        self.loc_choice = tk.StringVar(value="dept")
        rb1 = ttk.Radiobutton(frm_loc, text="Département(s)", value="dept", variable=self.loc_choice)
        rb2 = ttk.Radiobutton(frm_loc, text="Autour d'une commune (INSEE)", value="commune", variable=self.loc_choice)
        rb3 = ttk.Radiobutton(frm_loc, text="Aucun (France entière)", value="none", variable=self.loc_choice)
        rb1.grid(row=0, column=0, sticky="w")
        rb2.grid(row=0, column=1, sticky="w")
        rb3.grid(row=0, column=2, sticky="w")

        ttk.Label(frm_loc, text="Département(s):").grid(row=1, column=0, sticky="e", padx=4)
        self.ent_dept = ttk.Entry(frm_loc)
        self.ent_dept.insert(0, str(self.cfg.default_dept or ""))
        self.ent_dept.grid(row=1, column=1, sticky="we", padx=4)
        ttk.Label(frm_loc, text="Commune (nom ou INSEE):").grid(row=2, column=0, sticky="e", padx=4)
        self.ent_commune = ttk.Entry(frm_loc)
        self.ent_commune.grid(row=2, column=1, sticky="we", padx=4)
        ttk.Label(frm_loc, text="Distance (km):").grid(row=2, column=2, sticky="e", padx=4)
        self.ent_dist = ttk.Entry(frm_loc, width=7)
        self.ent_dist.insert(0, str(self.cfg.default_radius_km))
        self.ent_dist.grid(row=2, column=3, sticky="w", padx=4)
        frm_loc.columnconfigure(1, weight=1)

        # Time & Export
        frm_tx = ttk.LabelFrame(self, text="Fenêtre, rémunération et export")
        frm_tx.pack(fill=tk.X, padx=10, pady=8)
        ttk.Label(frm_tx, text="Jours (1,3,7,14,31):").grid(row=0, column=0, sticky="e")
        self.ent_days = ttk.Entry(frm_tx, width=6)
        self.ent_days.insert(0, "7")
        self.ent_days.grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(frm_tx, text="Top N:").grid(row=0, column=2, sticky="e")
        self.ent_top = ttk.Entry(frm_tx, width=8)
        self.ent_top.insert(0, "100")
        self.ent_top.grid(row=0, column=3, sticky="w", padx=6)
        ttk.Label(frm_tx, text="Format:").grid(row=0, column=4, sticky="e")
        self.var_fmt = tk.StringVar(value="md")
        ttk.OptionMenu(frm_tx, self.var_fmt, "md", "md", "txt", "html", "csv", "jsonl").grid(row=0, column=5, sticky="w")
        self.var_full = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm_tx, text="Description complète (txt/md)", variable=self.var_full).grid(row=0, column=6, sticky="w", padx=6)
        # Salary min
        ttk.Label(frm_tx, text="Salaire min (€/mois):").grid(row=1, column=0, sticky="e")
        self.ent_salary = ttk.Entry(frm_tx, width=10)
        self.ent_salary.grid(row=1, column=1, sticky="w", padx=6)

        # Buttons
        frm_btn = ttk.Frame(self)
        frm_btn.pack(fill=tk.X, padx=10, pady=6)
        self.var_clear = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm_btn, text="Nettoyer la base avant la recherche", variable=self.var_clear).pack(side=tk.LEFT, padx=6)
        self.btn_run = ttk.Button(frm_btn, text="Lancer", command=self._on_run)
        self.btn_run.pack(side=tk.LEFT)
        ttk.Button(frm_btn, text="Ouvrir le dossier de sortie", command=lambda: _open_folder(os.path.join("data", "out"))).pack(side=tk.LEFT, padx=8)
        ttk.Button(frm_btn, text="Copier le prompt IA", command=self._copy_prompt).pack(side=tk.LEFT)

        # Log area
        self.log = ScrolledText(self, height=16)
        self.log.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        self._log("Prêt. Sélectionnez vos options puis cliquez sur Lancer.")
        # Initialize defaults based on domain
        self._apply_domain_defaults()

    def _apply_domain_defaults(self):
        label = self.var_domain.get() if hasattr(self, 'var_domain') else (_DOMAINS[1][0] if len(_DOMAINS) > 1 else _DOMAINS[0][0])
        # Reset categories (aucune pré-sélection)
        if hasattr(self, 'var_cats'):
            for v in self.var_cats:
                v.set(False)
        # No auto-fill of keywords; only show a hint based on domain
        hint = ""
        for name, kws in _DOMAINS:
            if name == label:
                hint = "Exemples: " + ", ".join(kws[:6]) if kws else ""
                break
        if hasattr(self, 'lbl_kw_hint'):
            self.lbl_kw_hint.config(text=hint)
        if hasattr(self, 'ent_kw'):
            self.ent_kw.delete(0, tk.END)
        # Apply other numeric defaults if provided
        # Apply location/time defaults only (no categories/keywords auto-fill)
        prof = self.profile if isinstance(self.profile, dict) else {}
        try:
            if prof.get("published_since_days") and hasattr(self, 'ent_days'):
                self.ent_days.delete(0, tk.END)
                self.ent_days.insert(0, str(int(prof["published_since_days"])) )
            if prof.get("topn") and hasattr(self, 'ent_top'):
                self.ent_top.delete(0, tk.END)
                self.ent_top.insert(0, str(int(prof["topn"])) )
            if prof.get("export_format") and hasattr(self, 'var_fmt'):
                self.var_fmt.set(str(prof["export_format"]).lower())
            if "full_description" in prof and hasattr(self, 'var_full'):
                self.var_full.set(bool(prof["full_description"]))
            if prof.get("dept") and hasattr(self, 'ent_dept'):
                self.ent_dept.delete(0, tk.END)
                self.ent_dept.insert(0, str(prof["dept"]))
            if prof.get("distance_km") and hasattr(self, 'ent_dist'):
                self.ent_dist.delete(0, tk.END)
                self.ent_dist.insert(0, str(int(prof["distance_km"])) )
            if prof.get("min_salary_monthly") is not None and hasattr(self, 'ent_salary'):
                self.ent_salary.delete(0, tk.END)
                self.ent_salary.insert(0, str(prof["min_salary_monthly"]))
        except Exception:
            pass

    def _copy_prompt(self):
        text = _ai_prompt_text("<votre-fichier-export>.")
        try:
            self.master.clipboard_clear()
            self.master.clipboard_append(text)
            self.master.update()  # now it stays on the clipboard
            messagebox.showinfo("Copié", "Prompt IA copié dans le presse-papiers.")
        except Exception:
            self._log("Impossible de copier dans le presse-papiers.")

    def _log(self, msg: str):
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.update_idletasks()

    def _gather_inputs(self) -> dict[str, Any]:
        kw: list[str] = []
        for var, (_, lst) in zip(self.var_cats, _CATEGORIES):
            if var.get():
                kw.extend(lst)
        extra = self.ent_kw.get().strip()
        if extra:
            kw.extend([k.strip() for k in extra.split(",") if k.strip()])
        seen = set()
        kw = [k for k in kw if not (k in seen or seen.add(k))] or self.cfg.default_keywords

        loc_mode = self.loc_choice.get()
        dept = self.ent_dept.get().strip() if loc_mode == "dept" else None
        commune = self.ent_commune.get().strip() if loc_mode == "commune" else None
        distance_km = None
        if commune:
            try:
                distance_km = int(self.ent_dist.get().strip())
            except Exception:
                distance_km = self.cfg.default_radius_km

        try:
            days = int(self.ent_days.get().strip())
        except Exception:
            days = 7
        try:
            topn = int(self.ent_top.get().strip())
        except Exception:
            topn = 100
        fmt = self.var_fmt.get().lower()
        desc_chars = -1 if self.var_full.get() and fmt in ("md", "txt") else (500 if fmt == "md" else 400)
        try:
            min_salary = float(self.ent_salary.get().strip().replace(",", ".")) if self.ent_salary.get().strip() else None
        except Exception:
            min_salary = None

        return dict(
            keywords=kw,
            dept=dept,
            commune=commune,
            distance_km=distance_km,
            days=days,
            topn=topn,
            fmt=fmt,
            desc_chars=desc_chars,
            min_salary=min_salary,
        )

    def _on_run(self):
        self.btn_run.configure(state=tk.DISABLED)
        self._log("Vérification de la base…")
        try:
            init_db()
        except Exception as e:
            messagebox.showerror("Erreur DB", str(e))
            self.btn_run.configure(state=tk.NORMAL)
            return
        # Optional: clear DB before run
        if self.var_clear.get():
            try:
                from .storage import clear_offers
                clear_offers()
                self._log("Base nettoyée (table offers vidée).")
            except Exception as e:
                messagebox.showerror("Erreur DB", f"Nettoyage impossible: {e}")
                self.btn_run.configure(state=tk.NORMAL)
                return
        params = self._gather_inputs()
        # Convert name → INSEE when using commune mode
        if self.loc_choice.get() == "commune" and params.get("commune"):
            from .geocode import to_insee
            code, matched = to_insee(str(params.get("commune")))
            if not code:
                messagebox.showerror(
                    "Commune inconnue",
                    "Saisissez un nom de ville connu ou un code INSEE (ex: Mulhouse ou 68224).",
                )
                self.btn_run.configure(state=tk.NORMAL)
                return
            if matched and matched.upper() != code:
                self._log(f"Commune convertie: {matched} → {code}")
            params["commune"] = code
        self._log("Récupération des offres (cela peut prendre un moment)…")
        threading.Thread(target=self._worker, args=(params,), daemon=True).start()

    def _worker(self, params: dict[str, Any]):
        try:
            # Fetch
            fargs = Namespace(
                keywords=",".join(params["keywords"]),
                rome=None,
                auto_rome=False,
                dept=params["dept"],
                commune=params["commune"],
                distance_km=params["distance_km"],
                radius_km=None,
                limit=100,
                page=0,
                sort=1,
                published_since_days=params["days"],
                min_creation=None,
                max_creation=None,
                origine_offre=None,
                fetch_all=True,
                max_pages=10,
                no_smart_filter=True,
            )
            cmd_fetch(fargs)

            # Export
            rows = query_offers(
                days=params["days"],
                from_date=None,
                to_date=None,
                status=None,
                min_score=None,
                min_salary_monthly=params.get("min_salary"),
                limit=params["topn"],
                order_by="score_desc",
            )
            fmt = params["fmt"]
            if fmt == "txt":
                out_path = export_txt(rows, None, desc_chars=params["desc_chars"]) 
            elif fmt == "md":
                out_path = export_md(rows, None, desc_chars=params["desc_chars"]) 
            elif fmt == "csv":
                out_path = export_csv(rows, None)
            else:
                out_path = export_jsonl(rows, None)

            self._log(f"Export terminé: {out_path}")
            guide = _ai_prompt_text(out_path)
            try:
                with open(os.path.join("data", "out", "ai_prompt_example.txt"), "w", encoding="utf-8") as f:
                    f.write(guide)
                self._log("Guide IA enregistré: data/out/ai_prompt_example.txt")
            except Exception:
                pass
            self._log("Ouvrez le dossier de sortie pour consulter le fichier.")
        except Exception as e:
            messagebox.showerror("Erreur", str(e))
        finally:
            self.btn_run.configure(state=tk.NORMAL)


def main(profile_name: str | None = None) -> None:
    root = tk.Tk()
    # Use ttk theme if available
    try:
        style = ttk.Style()
        if sys.platform == "darwin":
            style.theme_use("aqua")
        else:
            style.theme_use(style.theme_use())  # keep default
    except Exception:
        pass
    App(root, profile_name=profile_name)
    root.mainloop()
